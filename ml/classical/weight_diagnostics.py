"""Controlled LightGBM/CatBoost weighting and validation-threshold diagnostics."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, precision_recall_fscore_support)
from threadpoolctl import threadpool_limits

from benchmark import LABELS, SEED, RSSMonitor, class_weights, feature_matrix, metrics, now_iso
from predictor import PredictionAdapter

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("NEURON5_WEIGHT_OUT", str(BASE / "results_weight_diagnostics_70_20_10")))
OUT.mkdir(parents=True, exist_ok=True)
PROGRESS = OUT / "progress.json"
CSV_RESULTS = OUT / "weight_results.csv"
OOF_CSV = OUT / "oof_predictions.csv"
VAL_CSV = OUT / "validation_predictions.csv"
WEIGHTS = [(1.0,1.0,1.0),(1.0,1.5,1.0),(1.0,2.0,1.0),(1.0,3.0,1.0),
           (1.0,1.5,2.0),(1.0,2.0,2.0),(1.0,3.0,3.0)] # TRUE, FALSE, UNSURE
LABEL_INDEX = {label:i for i,label in enumerate(LABELS)}


def dump_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    os.replace(tmp,path)


def tick(state, message):
    state["updated_at"]=now_iso(); state["message"]=message
    if state.get("start_clock"):
        state["elapsed_seconds"]=time.perf_counter()-state["start_clock"]
    planned=state.get("planned_by_family",{})
    completed=state.get("completed_by_family",{})
    samples=state.get("unit_seconds_by_family",{})
    fallbacks={"lightgbm_cv":2.0,"catboost_cv":20.0,"lightgbm_validation":2.0,"catboost_validation":30.0}
    eta=0.0
    for family,count in planned.items():
        remaining=max(0,int(count)-int(completed.get(family,0)))
        observed=samples.get(family,[])
        eta+=remaining*(float(np.median(observed)) if observed else fallbacks[family])
    state["eta_seconds_remaining"]=eta if planned else None
    if state["eta_seconds_remaining"] is not None:
        state["projected_finish_utc"]=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=state["eta_seconds_remaining"])).isoformat(timespec="seconds")
    dump_json(PROGRESS,state)
    eta=round(state["eta_seconds_remaining"]) if state["eta_seconds_remaining"] is not None else "uncalibrated"
    print(f"[{state['updated_at']}] {message}; unit {state['completed_units']}/{state['planned_units']}; elapsed {state['elapsed_seconds']:.1f}s; ETA {eta}s",flush=True)


def exact_weights(vector):
    # LGBM's encoded labels are lexicographically ordered: false, true, unsure.
    return {"false":float(vector[1]),"true":float(vector[0]),"unsure":float(vector[2])}


def cat_weights(vector):
    # benchmark LABELS order is false, true, unsure.
    return [float(vector[1]),float(vector[0]),float(vector[2])]


def align_probs(est, x):
    raw=est.predict_proba(x); classes=list(est.classes_)
    out=np.zeros((len(raw),3),dtype=np.float64)
    for j,c in enumerate(classes): out[:,LABEL_INDEX[str(c)]]=raw[:,j]
    sums=out.sum(axis=1,keepdims=True)
    return np.divide(out,sums,out=np.zeros_like(out),where=sums!=0)


def classification_metrics(y_true, pred):
    p,r,f,s=precision_recall_fscore_support(y_true,pred,labels=LABELS,zero_division=0)
    return {"accuracy":float(accuracy_score(y_true,pred)),"balanced_accuracy":float(balanced_accuracy_score(y_true,pred)),
            "macro_f1":float(f1_score(y_true,pred,labels=LABELS,average="macro",zero_division=0)),
            "classes":{c:{"precision":float(p[i]),"recall":float(r[i]),"f1":float(f[i]),"support":int(s[i])} for i,c in enumerate(LABELS)},
            "confusion_matrix_labels":LABELS,"confusion_matrix":confusion_matrix(y_true,pred,labels=LABELS).tolist()}


def make_estimator(family, vector, y_train, cat_cls, lgb_cls):
    if family=="lightgbm":
        return lgb_cls(objective="multiclass",num_class=3,num_leaves=15,n_estimators=300,
                       learning_rate=0.05,min_child_samples=20,reg_lambda=1,n_jobs=2,
                       random_state=SEED,class_weight=exact_weights(vector),verbosity=-1)
    return cat_cls(loss_function="MultiClass",depth=5,iterations=300,learning_rate=0.05,l2_leaf_reg=3,
                   early_stopping_rounds=30,thread_count=2,random_seed=SEED,verbose=False,
                   allow_writing_files=False,class_weights=cat_weights(vector),eval_metric="MultiClass",
                   task_type="CPU")


def fit_cv(est,family,xtr,ytr,xva,yva):
    if family=="lightgbm":
        from lightgbm import early_stopping,log_evaluation
        est.fit(xtr,ytr,eval_set=[(xva,yva)],callbacks=[early_stopping(30,verbose=False),log_evaluation(0)])
    else: est.fit(xtr,ytr,eval_set=(xva,yva),verbose=False)


def append_rows(path, rows, fields):
    exists=path.exists()
    with path.open("a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        if not exists:w.writeheader()
        w.writerows(rows)


def prediction_rows(rows,indices,y,probs,config,split_name,folds=None):
    out=[]; labels=np.asarray(LABELS)[np.argmax(probs,axis=1)]
    for j,ix in enumerate(indices):
        part=split_name if folds is None else f"fold_{int(folds[j])}"
        out.append({"row_id":rows[int(ix)]["id"],"true_label":y[int(ix)],"predicted_label":str(labels[j]),
                    "probability_true":float(probs[j,LABEL_INDEX["true"]]),
                    "probability_false":float(probs[j,LABEL_INDEX["false"]]),
                    "probability_unsure":float(probs[j,LABEL_INDEX["unsure"]]),
                    "model_configuration":config,"fold_or_split":part})
    return out


def build_feature_categories(row):
    try: facts=json.loads(row.get("form") or "[]")
    except (ValueError,TypeError): facts=[]
    facts=[x for x in facts if isinstance(x,dict)] if isinstance(facts,list) else []
    entities=sorted({str(x.get("subject") or "unknown") for x in facts}) or ["no_parsed_entity"]
    attrs=sorted({str(x.get("attribute") or "unknown") for x in facts}) or ["no_parsed_attribute"]
    kinds=sorted({str((x.get("value") or {}).get("kind") or "unknown") for x in facts}) or ["no_parsed_value_kind"]
    text=row.get("text",""); date=row.get("date","")
    numeric=bool(re.search(r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:%|percent|million|billion|thousand|km|m|kg|gb|mb|hz|\$|€|£)?",text,re.I))
    negation=bool(re.search(r"\b(?:not|no|never|without|neither|nor|isn't|wasn't|aren't|weren't|doesn't|didn't|hasn't|haven't|won't|can't|cannot)\b",text,re.I))
    multi=len(facts)>1
    return {"entities":entities,"attributes":attrs,"value_kinds":kinds,"date":date,
            "year":date[:4] if len(date)>=4 else "unknown_date","numeric":numeric,"negation":negation,
            "multi_fact":multi,"fact_count":len(facts)}


def threshold_predictions(probs,t_false=1.0,t_unsure=1.0):
    # Class-specific score scaling is equivalent to lowering that class's
    # decision threshold relative to the unchanged TRUE score.
    scores=probs.copy()
    scores[:,LABEL_INDEX["false"]]/=t_false
    scores[:,LABEL_INDEX["unsure"]]/=t_unsure
    return np.asarray(LABELS)[np.argmax(scores,axis=1)]


def main():
    os.environ.update({"OMP_NUM_THREADS":"2","MKL_NUM_THREADS":"2","OPENBLAS_NUM_THREADS":"2","TOKENIZERS_PARALLELISM":"false"})
    started=time.perf_counter()
    if PROGRESS.exists():
        raise FileExistsError(f"Refusing to overwrite existing experiment output: {OUT}. Set NEURON5_WEIGHT_OUT to a fresh directory to preserve it.")
    with (ROOT/"ml/shared/splits.csv").open(encoding="utf-8-sig",newline="") as f: split_map={x["id"]:x["split"] for x in csv.DictReader(f)}
    with (ROOT/"ml/shared/cv10_folds.csv").open(encoding="utf-8-sig",newline="") as f: fold_map={x["id"]:int(x["fold"]) for x in csv.DictReader(f)}
    # Materialize only train and validation records. The outer-test rows are
    # skipped before labels/forms are read or features are constructed.
    data_path=ROOT/"data/practice.csv"
    rows=[]
    with data_path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        for raw in reader:
            row_id=raw["id"]
            if split_map.get(row_id) not in {"train","validation"}: continue
            item={"id":row_id,"text":raw["text"],"date":raw["date"],"label":raw["label"].strip().lower()}
            if split_map[row_id]=="validation": item["form"]=raw.get("form","")
            rows.append(item)
    ids=[r["id"] for r in rows]
    if len(split_map)!=len(set(split_map)) or set(split_map)-set(ids)-{x for x,s in split_map.items() if s=="test"}:raise ValueError("split manifest row coverage mismatch")
    train=np.array([i for i,x in enumerate(ids) if split_map[x]=="train"],dtype=int)
    val=np.array([i for i,x in enumerate(ids) if split_map[x]=="validation"],dtype=int)
    if set(ids)!={x for x,s in split_map.items() if s in {"train","validation"}}:raise ValueError("train/validation manifest coverage mismatch")
    lex=json.loads((ROOT/"data/lexicon.json").read_text(encoding="utf-8"))
    folds=np.array([fold_map[ids[i]] for i in train],dtype=int)
    # Form values are stripped from feature rows; validation forms are retained
    # in `rows` only for post-prediction error characterization.
    y_all=np.array([r["label"] for r in rows])
    feature_rows=[{"id":r["id"],"text":r["text"],"date":r["date"]} for r in rows]
    y=y_all.copy()
    fold_configs=[("lightgbm",15,1,w) for w in WEIGHTS]+[("lightgbm",15,5,w) for w in WEIGHTS]
    # CatBoost will repeat the unweighted baseline, the top LightGBM CV macro-F1
    # weighting, and the best accuracy-constrained minority-recall weighting.
    state={"status":"RUNNING","started_at":now_iso(),"start_clock":started,"pid":os.getpid(),
           "protocol":"targeted weight diagnostics; outer test labels/forms withheld and never evaluated",
           "train_rows":len(train),"validation_rows":len(val),"cv_folds":10,"planned_configurations":17,
           "planned_units":187,"completed_units":0,"units_remaining":187,"unit_seconds":[],
           "planned_by_family":{"lightgbm_cv":140,"catboost_cv":30,"lightgbm_validation":14,"catboost_validation":3},
           "completed_by_family":{"lightgbm_cv":0,"catboost_cv":0,"lightgbm_validation":0,"catboost_validation":0},
           "unit_seconds_by_family":{"lightgbm_cv":[],"catboost_cv":[],"lightgbm_validation":[],"catboost_validation":[]},
           "preliminary_eta_seconds_uncalibrated":140*2+30*20+14*2+3*30,"phase":"preparing","current_family":None,
           "current_configuration":None,"current_fold":None}
    tick(state,"startup: 14 LightGBM CV configs; CatBoost CV weight vectors selected after LightGBM; preliminary duration estimate UNCALIBRATED")
    try:
        try:
            from catboost import CatBoostClassifier
        except Exception as exc: CatBoostClassifier=None; state["catboost_import_error"]=repr(exc)
        from lightgbm import LGBMClassifier,early_stopping,log_evaluation
        prep_t=time.perf_counter(); prepared={}
        for fold in range(10):
            va=train[folds==fold];tr=train[folds!=fold]
            x,builder=feature_matrix(feature_rows,lex,tr)
            prepared[fold]={"x":x,"builder":builder,"train":tr,"valid":va}
        prep_sec=time.perf_counter()-prep_t
        weights_audit={"order":["true","false","unsure"],"train_counts":dict(Counter(y[train])),"modes":{},"cv_training_fold_weight_ranges":{}}
        for mode in ("moderate","balanced"):
            ww=class_weights(mode,y[train]);weights_audit["modes"][mode]={c:ww[c] for c in ("true","false","unsure")}
        perfold={m:defaultdict(list) for m in ("moderate","balanced")}
        for k in range(10):
            tr=train[folds!=k]
            for mode in perfold:
                ww=class_weights(mode,y[tr])
                for c in ("true","false","unsure"):perfold[mode][c].append(ww[c])
        for mode in perfold:weights_audit["cv_training_fold_weight_ranges"][mode]={c:{"mean":float(np.mean(v)),"min":float(np.min(v)),"max":float(np.max(v))} for c,v in perfold[mode].items()}
        weights_audit["custom_candidate_vectors_T_F_U"]=[list(w) for w in WEIGHTS]
        dump_json(OUT/"class_weights.json",weights_audit)
        state["feature_preparation_seconds"]=prep_sec;state["phase"]="lightgbm_cv";tick(state,f"prepared 10 fold-local feature matrices in {prep_sec:.2f}s")
        all_records=[];oof_rows=[];cv_duration_by_candidate={};family_gpu="CPU"
        def run_cv_config(config):
            nonlocal family_gpu
            family,leaves,reg,vector=config
            config_id=f"{family}:leaves{leaves}:lambda{reg}:T{vector[0]:g}-F{vector[1]:g}-U{vector[2]:g}"
            oof=np.zeros((len(rows),3),dtype=np.float64);fold_scores=[];fit_total=0.;pred_total=0.
            for fold in range(10):
                state["current_family"]=family;state["current_configuration"]=config_id;state["current_fold"]=fold
                fold_start=time.perf_counter();d=prepared[fold];tr,va=d["train"],d["valid"]
                fam_gpu=family_gpu if family=="catboost" else "CPU"
                est=make_estimator(family,vector,y[tr],CatBoostClassifier,LGBMClassifier)
                try:
                    xtr=d["x"][tr].toarray().astype(np.float32) if family=="catboost" else d["x"][tr]
                    xva=d["x"][va].toarray().astype(np.float32) if family=="catboost" else d["x"][va]
                    with threadpool_limits(limits=2):fit_cv(est,family,xtr,y[tr],xva,y[va])
                except Exception as exc:
                    if family!="catboost" or family_gpu!="GPU":raise
                    family_gpu="CPU";state["catboost_gpu_fallback"]=f"{type(exc).__name__}: {exc}"
                    est=CatBoostClassifier(loss_function="MultiClass",depth=5,iterations=300,learning_rate=.05,l2_leaf_reg=3,
                          early_stopping_rounds=30,thread_count=2,random_seed=SEED,verbose=False,allow_writing_files=False,
                          class_weights=cat_weights(vector),eval_metric="MultiClass",task_type="CPU")
                    with threadpool_limits(limits=2):fit_cv(est,family,d["x"][tr].toarray().astype(np.float32),y[tr],d["x"][va].toarray().astype(np.float32),y[va])
                fit_sec=time.perf_counter()-fold_start;fit_total+=fit_sec
                xva=d["x"][va].toarray().astype(np.float32) if family=="catboost" else d["x"][va]
                pred_start=time.perf_counter()
                with threadpool_limits(limits=2):p=align_probs(est,xva)
                pred_sec=time.perf_counter()-pred_start;pred_total+=pred_sec;oof[va]=p
                fm=metrics(y[va],p);fold_scores.append({"fold":fold,"rows":len(va),"fit_seconds":fit_sec,"predict_seconds":pred_sec,"macro_f1":fm["macro_f1"]})
                append_rows(OOF_CSV,prediction_rows(rows,va,y,p,config_id,"cv",np.full(len(va),fold)),
                    ["row_id","true_label","predicted_label","probability_true","probability_false","probability_unsure","model_configuration","fold_or_split"])
                unit=time.perf_counter()-fold_start;state["completed_units"]+=1;state["units_remaining"]=state["planned_units"]-state["completed_units"]
                phase_family=f"{family}_cv";state["completed_by_family"][phase_family]+=1
                state["unit_seconds"].append(unit);state["unit_seconds_by_family"][phase_family].append(unit);state["current_fold_metrics"]=fold_scores
                tick(state,f"finished {config_id} CV fold {fold+1}/10; macro-F1={fm['macro_f1']:.4f}")
            cvm=metrics(y[train],oof[train]); record={"family":family,"configuration_id":config_id,"base":{"num_leaves":leaves,"reg_lambda":reg,"depth":5 if family=="catboost" else None,"l2_leaf_reg":3 if family=="catboost" else None},
                "weights_true_false_unsure":list(vector),"cv_metrics":{k:v for k,v in cvm.items() if k not in {"predicted","confidence"}},
                "fold_macro_f1_mean":float(np.mean([x["macro_f1"] for x in fold_scores])),"fold_macro_f1_std":float(np.std([x["macro_f1"] for x in fold_scores])),
                "folds":fold_scores,"fit_seconds_total":fit_total,"prediction_seconds_total":pred_total,
                "training_hardware":("GPU" if family=="catboost" and family_gpu=="GPU" else "CPU")}
            all_records.append(record);cv_duration_by_candidate[config_id]=fit_total
            dump_json(OUT/(config_id.replace(":","_")+"_cv.json"),record)
            return record,oof
        lgb_records=[]
        for config in fold_configs:
            rec,oof=run_cv_config(config);lgb_records.append((rec,oof))
        baseline=next(r for r,_ in lgb_records if r["base"]["reg_lambda"]==1 and r["weights_true_false_unsure"]==[1.,1.,1.])
        baseline_acc=baseline["cv_metrics"]["accuracy"]
        # Chosen weights cover baseline, best macro-F1, and best minority recall
        # among candidates with no more than a 2 point CV accuracy loss.
        eligible=[r for r,_ in lgb_records if r["cv_metrics"]["accuracy"]>=baseline_acc-.02]
        top_macro=max(lgb_records,key=lambda z:z[0]["cv_metrics"]["macro_f1"])[0]
        top_minor=max(eligible,key=lambda r:r["cv_metrics"]["classes"]["false"]["recall"]+r["cv_metrics"]["classes"]["unsure"]["recall"])
        cat_vectors=[]
        for vector in ([1.,1.,1.],top_macro["weights_true_false_unsure"],top_minor["weights_true_false_unsure"]):
            tup=tuple(vector)
            if tup not in cat_vectors:cat_vectors.append(tup)
        while len(cat_vectors)<3:
            candidate=next((tuple(w) for w in WEIGHTS if tuple(w) not in cat_vectors),None)
            if candidate is None:break
            cat_vectors.append(candidate)
        cat_configs=[("catboost",None,None,v) for v in cat_vectors]
        state["catboost_weight_vectors_selected"]=[list(x) for x in cat_vectors]
        state["phase"]="catboost_cv";tick(state,"selected three CatBoost weights from LightGBM CV: baseline, best CV macro-F1, and best minority recall within 2pp accuracy")
        for config in cat_configs:run_cv_config(config)
        # For each candidate, refit only on train; validation labels are reserved
        # for scoring/threshold diagnostics and do not drive tree early stopping.
        state["phase"]="validation_refits";cv_best=sorted(all_records,key=lambda r:r["cv_metrics"]["macro_f1"],reverse=True)
        baseline_all=next(r for r in all_records if r["family"]=="lightgbm" and r["base"]["reg_lambda"]==1 and r["weights_true_false_unsure"]==[1.,1.,1.])
        best_acc=max(r["cv_metrics"]["accuracy"] for r in all_records)
        best_macro=max(all_records,key=lambda r:r["cv_metrics"]["macro_f1"])
        eligible_all=[r for r in all_records if r["family"]=="lightgbm" and r["cv_metrics"]["accuracy"]>=baseline_all["cv_metrics"]["accuracy"]-.02]
        recommended=max(eligible_all,key=lambda r:(r["cv_metrics"]["macro_f1"],r["cv_metrics"]["balanced_accuracy"])) if eligible_all else baseline_all
        state["selection_ids"]={"accuracy":max(all_records,key=lambda r:r["cv_metrics"]["accuracy"])["configuration_id"],"macro_f1":best_macro["configuration_id"],
                                 "accuracy_constrained_lightgbm":recommended["configuration_id"],"constraint":"within 2 percentage points of LightGBM (15 leaves, lambda 1, weights 1/1/1) CV accuracy"}
        all_val=[];val_records=[];feature_train,train_builder=feature_matrix(feature_rows,lex,train)
        for ix,rec in enumerate(all_records):
            family=rec["family"];vector=rec["weights_true_false_unsure"]
            est=make_estimator(family,vector,y[train],CatBoostClassifier,LGBMClassifier)
            dense=feature_train.toarray().astype(np.float32) if family=="catboost" else feature_train
            mon=RSSMonitor();mon.start();tfit=time.perf_counter()
            with threadpool_limits(limits=2):est.fit(dense[train],y[train])
            fit_val=time.perf_counter()-tfit;mon.stop()
            fam_dir=OUT/"models"/rec["configuration_id"].replace(":","_");fam_dir.mkdir(parents=True,exist_ok=True)
            ts=time.perf_counter();native=None
            if family=="catboost":
                native=fam_dir/"model.cbm";est.save_model(str(native))
                cpu=CatBoostClassifier(task_type="CPU",thread_count=2,verbose=False);cpu.load_model(str(native));infer_est=cpu
            else:infer_est=est
            artifact=fam_dir/"adapter.joblib"
            builder={k:v for k,v in train_builder.items() if k not in {"char_matrix","info"}}
            joblib.dump(PredictionAdapter(infer_est,builder,tuple(LABELS),family),artifact,compress=3)
            size=artifact.stat().st_size+(native.stat().st_size if native else 0);ser=time.perf_counter()-ts
            adapter=joblib.load(artifact);val_rows=[rows[int(i)] for i in val]
            tp=time.perf_counter()
            with threadpool_limits(limits=2):pv=adapter.predict_proba(val_rows)
            predict_sec=time.perf_counter()-tp;vm=metrics(y[val],pv)
            val_conf=prediction_rows(rows,val,y,pv,rec["configuration_id"],"validation")
            append_rows(VAL_CSV,val_conf,["row_id","true_label","predicted_label","probability_true","probability_false","probability_unsure","model_configuration","fold_or_split"])
            all_val.append((rec,pv));val_records.append({"configuration_id":rec["configuration_id"],"validation_metrics":{k:v for k,v in vm.items() if k not in {"predicted","confidence"}},
                "fit_seconds":fit_val,"validation_predict_seconds":predict_sec,"validation_rows_per_second":len(val)/max(predict_sec,1e-9),"serialization_seconds":ser,
                "model_size_bytes":size,"peak_rss_mb":mon.peak,"artifact":str(artifact.relative_to(ROOT))})
            # All configurations are being written as requested. Final recommendation is selected on CV;
            # validation metrics remain an independent confirmation layer.
            cv_rec={k:rec[k] for k in ("family","configuration_id","weights_true_false_unsure","base","cv_metrics","fold_macro_f1_mean","fold_macro_f1_std","fit_seconds_total","training_hardware")}
            result={**cv_rec,**val_records[-1]}
            dump_json(fam_dir/"metrics.json",result)
            state["completed_units"]+=1;state["units_remaining"]=state["planned_units"]-state["completed_units"]
            # Store measured work per unit, enabling a durable calibrated ETA.
            unit=fit_val+predict_sec+ser;phase_family=f"{family}_validation";state["completed_by_family"][phase_family]+=1
            state["unit_seconds"].append(unit);state["unit_seconds_by_family"][phase_family].append(unit)
            tick(state,f"validation scored {rec['configuration_id']}; macro-F1={vm['macro_f1']:.4f}")
        # Recommend the CV-selected LightGBM weight candidate. The validation split
        # reports it separately; we only use validation labels below for threshold search.
        chosen_rec=next(r for r in all_records if r["configuration_id"]==recommended["configuration_id"])
        chosen_val=next(p for r,p in all_val if r["configuration_id"]==chosen_rec["configuration_id"])
        base_valrec=next(p for r,p in all_val if r["configuration_id"]==baseline_all["configuration_id"])
        chosen_argmax=np.asarray(LABELS)[np.argmax(chosen_val,axis=1)]
        base_val_metrics=classification_metrics(y[val],chosen_argmax)
        threshold_rows=[];threshold_pool=[]
        thresholds=[0.2,0.3,0.4,0.5,0.6,0.8,1.0]
        for tf in thresholds:
            for tu in thresholds:
                pred=threshold_predictions(chosen_val,tf,tu);m=classification_metrics(y[val],pred)
                row={"policy":"argmax" if tf==1 and tu==1 else ("false_threshold" if tu==1 else ("unsure_threshold" if tf==1 else "combined_threshold")),
                     "false_threshold":tf,"unsure_threshold":tu,"accuracy":m["accuracy"],"accuracy_delta_vs_argmax":m["accuracy"]-base_val_metrics["accuracy"],
                     "balanced_accuracy":m["balanced_accuracy"],"macro_f1":m["macro_f1"],
                     "false_precision":m["classes"]["false"]["precision"],"false_recall":m["classes"]["false"]["recall"],"false_f1":m["classes"]["false"]["f1"],
                     "unsure_precision":m["classes"]["unsure"]["precision"],"unsure_recall":m["classes"]["unsure"]["recall"],"unsure_f1":m["classes"]["unsure"]["f1"],
                     "confusion_matrix":json.dumps(m["confusion_matrix"])}
                threshold_rows.append(row);threshold_pool.append((row,m))
        fields=list(threshold_rows[0]);append_rows(OUT/"threshold_analysis.csv",threshold_rows,fields)
        constrained=[(r,m) for r,m in threshold_pool if r["accuracy"]>=base_val_metrics["accuracy"]-.02]
        best_constrained=max(constrained,key=lambda z:(z[0]["macro_f1"],z[0]["balanced_accuracy"]))
        best_minor=max(constrained,key=lambda z:(z[0]["false_recall"]+z[0]["unsure_recall"],z[0]["macro_f1"]))
        best_accuracy=max(threshold_pool,key=lambda z:z[0]["accuracy"])
        baseline_threshold=next((r,m) for r,m in threshold_pool if r["false_threshold"]==1 and r["unsure_threshold"]==1)
        threshold_summary={"source":"validation predictions only","selected_configuration":chosen_rec["configuration_id"],
          "baseline_argmax":baseline_threshold[0],"best_accuracy":best_accuracy[0],"best_macro_f1_with_accuracy_loss_at_most_2pp":best_constrained[0],
          "best_minority_recall_with_accuracy_loss_at_most_2pp":best_minor[0],"thresholds_tested_each_class":thresholds,
          "interpretation":"thresholds are validation-tuned; their validation metrics are not an unbiased test estimate"}
        dump_json(OUT/"threshold_summary.json",threshold_summary)
        # Choose baseline argmax for error analysis; also compute threshold policy counts.
        chosen_metrics=metrics(y[val],chosen_val);pred=np.asarray(chosen_metrics["predicted"]);val_errors=[]
        for j,ix in enumerate(val):
            if pred[j]==y[ix]:continue
            row=rows[int(ix)];cats=build_feature_categories(row)
            facts=json.loads(row.get("form") or "[]") if row.get("form") else []
            val_errors.append({"row_id":row["id"],"true_label":y[ix],"predicted_label":str(pred[j]),
                "probability_true":float(chosen_val[j,LABEL_INDEX["true"]]),"probability_false":float(chosen_val[j,LABEL_INDEX["false"]]),
                "probability_unsure":float(chosen_val[j,LABEL_INDEX["unsure"]]),"date":row["date"],"text":row["text"],
                "gold_facts_for_error_analysis_only":json.dumps(facts,ensure_ascii=False),"entity":json.dumps(cats["entities"],ensure_ascii=False),
                "attribute":json.dumps(cats["attributes"],ensure_ascii=False),"value_kind":json.dumps(cats["value_kinds"],ensure_ascii=False),
                "year":cats["year"],"numeric_claim":cats["numeric"],"negation":cats["negation"],"multi_fact":cats["multi_fact"],"fact_count":cats["fact_count"]})
        err_fields=list(val_errors[0]) if val_errors else ["row_id","true_label","predicted_label"]
        append_rows(OUT/"validation_errors.csv",val_errors,err_fields)
        incorrect_indices=[int(i) for i in np.where(pred!=y[val])[0]]
        rep_idx=incorrect_indices[:20]
        append_rows(OUT/"representative_incorrect_predictions.csv",[val_errors[incorrect_indices.index(j)] for j in rep_idx],err_fields)
        category_counts=defaultdict(Counter)
        error_records=val_errors
        for er in error_records:
            for cat in ("entity","attribute","value_kind","date","year","numeric_claim","negation","multi_fact","true_label"):
                try:value=json.loads(er[cat]) if cat in {"entity","attribute","value_kind"} else er[cat]
                except ValueError:value=er[cat]
                values=value if isinstance(value,list) else [value]
                for v in values:category_counts[cat][str(v)]+=1
        cat_rows=[]
        for cat,counts in category_counts.items():
            for value,count in counts.most_common():cat_rows.append({"dimension":cat,"value":value,"incorrect_rows":count})
        append_rows(OUT/"error_categories.csv",cat_rows,["dimension","value","incorrect_rows"])
        pred_false=pred=="false";actual_false=y[val]=="false"
        error_summary={"model_configuration":chosen_rec["configuration_id"],"validation_rows":len(val),"incorrect_rows":len(val_errors),
                       "representative_incorrect_rows_exported":len(rep_idx),"false_predictions":int(pred_false.sum()),
                       "correct_false_predictions_true_positives":int(np.sum(pred_false&actual_false)),
                       "false_alarms_false_predictions_on_true_or_unsure":int(np.sum(pred_false&~actual_false)),
                       "standard_argmax_metrics":{k:v for k,v in chosen_metrics.items() if k not in {"predicted","confidence"}},
                       "threshold_tuned_false_predictions":int(np.sum(threshold_predictions(chosen_val,best_constrained[0]["false_threshold"],best_constrained[0]["unsure_threshold"])=="false")),
                       "error_category_counts":{k:counts.most_common(20) for k,counts in category_counts.items()},
                       "note":"gold forms are joined only after predictions, for post-hoc error analysis; they are never features"}
        dump_json(OUT/"error_analysis.json",error_summary)
        # P0 audit/roadmap, based on actual foundation/runner interfaces.
        roadmap="""# Fact-aware feature roadmap based on P0\n\n## Existing P0 contract and interfaces\n\n`foundation.py` defines `TypedValue`, `AtomicFact`, `Lexicon`, `EvidenceRecord`, `TemporalObservation`, and `CandidateFact`. `parse_evidence_form` validates a supplied JSON fact list against the claimed-value schema and canonicalizes lexicon aliases. `observations` labels facts from true rows `confirmed_true`, false-row facts `row_false_atomic_status_unknown`, and unsure rows `row_unsure`. `evidence_audit` uses only confirmed-true observations for support, dated histories, comparisons, changes, event/date relations, and strict as-of counts. It intentionally does not treat the `false` row label as proof every fact in that row is false and does not infer persistence from past observations.\n\n`runner.py` reads `id,text,date,label` and a lexicon through `load_inputs`, runs `evidence_audit`, validates externally supplied candidates, and writes contract-compliant output. It has no text-to-fact semantic parser, verifier, retrieval layer, or prediction adapter. Runtime rows do not include gold `form`; validation/test forms are evaluation-only.\n\n## Features available now\n\nThe current classical builder uses word/character TF-IDF, row date and cyclic date metadata, lexicon entity/alias mentions, attribute-term flags, numeric/currency/month counts, and negation/temporal cue flags. These are computable identically at training and runtime from text/date/lexicon. Existing P0 can also parse already-supplied typed facts and audit the training-only true evidence if that evidence is bundled.\n\n## Next fact-aware increment (no second graph engine)\n\n1. Add one local text-to-`CandidateFact` parser interface using the P0 `AtomicFact`/`TypedValue` structures and lexicon canonicalization; measure parse coverage and unknown-entity/attribute rates. Train and runtime must call the same versioned parser.\n2. Freeze an evidence index from **training-partition-only** evidence, using P0 `TemporalObservation` and existing `evidence_audit` logic. Store provenance row IDs and observed dates; do not ingest validation/test forms. Reuse these structures rather than creating another knowledge graph.\n3. For parsed candidate facts, add features: exact/canonical subject-attribute match; typed kind match; unit/currency compatibility; normalized numeric difference only after compatible unit conversion; direct-date match and time since observation; counts of confirmed-true support and explicit typed conflicts; and parse/coverage indicators.\n4. Treat missing retrieval, incompatible types, and no evidence as unknown, not contradiction. Only count contradictions where a permitted source explicitly establishes an incompatible value for the same entity/attribute and relevant date. Never derive a false fact from a false-row label.\n5. Evaluate extraction coverage separately from label classification, then compare fact-aware features with this shared grouped CV. Keep the as-of date semantics explicit; historical truth does not establish current truth.\n\nNo P0 core files are changed by this diagnostic."""
        (OUT/"FEATURE_ROADMAP.md").write_text(roadmap,encoding="utf-8")
        # Summary includes CV / validation timing, size, calibration and class details.
        result_rows=[]
        for rec,valrec in zip(all_records,val_records):
            cm=rec["cv_metrics"];vm=valrec["validation_metrics"]
            result_rows.append({"configuration_id":rec["configuration_id"],"family":rec["family"],"weights_true_false_unsure":json.dumps(rec["weights_true_false_unsure"]),
              "base_parameters":json.dumps(rec["base"]),"cv_accuracy":cm["accuracy"],"cv_balanced_accuracy":cm["balanced_accuracy"],"cv_macro_f1":cm["macro_f1"],
              "cv_false_precision":cm["classes"]["false"]["precision"],"cv_false_recall":cm["classes"]["false"]["recall"],"cv_false_f1":cm["classes"]["false"]["f1"],"cv_false_support":cm["classes"]["false"]["support"],
              "cv_unsure_precision":cm["classes"]["unsure"]["precision"],"cv_unsure_recall":cm["classes"]["unsure"]["recall"],"cv_unsure_f1":cm["classes"]["unsure"]["f1"],"cv_unsure_support":cm["classes"]["unsure"]["support"],
              "cv_ece_10bin":cm["ece_10bin"],"cv_brier":cm["multiclass_brier"],"cv_confusion_matrix":json.dumps(cm["confusion_matrix"]),"fold_macro_f1_mean":rec["fold_macro_f1_mean"],"fold_macro_f1_std":rec["fold_macro_f1_std"],
              "validation_accuracy":vm["accuracy"],"validation_balanced_accuracy":vm["balanced_accuracy"],"validation_macro_f1":vm["macro_f1"],
              "validation_false_precision":vm["classes"]["false"]["precision"],"validation_false_recall":vm["classes"]["false"]["recall"],"validation_false_f1":vm["classes"]["false"]["f1"],
              "validation_unsure_precision":vm["classes"]["unsure"]["precision"],"validation_unsure_recall":vm["classes"]["unsure"]["recall"],"validation_unsure_f1":vm["classes"]["unsure"]["f1"],
              "validation_ece_10bin":vm["ece_10bin"],"validation_brier":vm["multiclass_brier"],"validation_confusion_matrix":json.dumps(vm["confusion_matrix"]),
              "cv_fit_seconds":rec["fit_seconds_total"],"validation_fit_seconds":valrec["fit_seconds"],"validation_inference_seconds":valrec["validation_predict_seconds"],
              "validation_rows_per_second":valrec["validation_rows_per_second"],"serialization_seconds":valrec["serialization_seconds"],"model_size_bytes":valrec["model_size_bytes"],"peak_rss_mb":valrec["peak_rss_mb"],"training_hardware":rec["training_hardware"]})
        append_rows(OUT/"weight_results.csv",result_rows,list(result_rows[0]))
        # Threshold tuning uses the CV-selected candidate's validation predictions only.
        best_val=metrics(y[val],chosen_val)
        report={"status":"completed","started_at":state["started_at"],"finished_at":now_iso(),"elapsed_seconds":time.perf_counter()-started,
          "counts":{"train":len(train),"validation":len(val),"outer_test":"withheld and not evaluated"},"fold_count":10,"feature_preparation_seconds":prep_sec,
          "class_weights":weights_audit,"cv_records":all_records,"validation_records":val_records,
          "cv_selection":{"baseline_unweighted":baseline_all["configuration_id"],"baseline_cv_accuracy":baseline_all["cv_metrics"]["accuracy"],
            "highest_cv_accuracy":max(r["cv_metrics"]["accuracy"] for r in all_records),"best_macro_f1":best_macro["configuration_id"],
            "best_macro_f1_value":best_macro["cv_metrics"]["macro_f1"],"recommended_accuracy_constrained":recommended["configuration_id"],
            "constraint":state["selection_ids"]["constraint"]},
          "threshold_analysis":threshold_summary,"error_analysis":error_summary,
          "leakage_note":"Grouped duplicate/fact-signature folds used. Shared subject-attribute histories can cross folds/partitions per splitting_audit.json.",
          "outer_test_status":"not loaded into any metric or model-selection computation"}
        dump_json(OUT/"summary.json",report)
        state.update({"status":"COMPLETED","finished_at":report["finished_at"],"projected_finish_utc":report["finished_at"],"units_remaining":0,"phase":"complete"})
        tick(state,f"completed; recommended CV candidate {recommended['configuration_id']}; validation macro-F1={best_val['macro_f1']:.4f}")
    except Exception as exc:
        state.update({"status":"FAILED","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc(),"finished_at":now_iso()})
        tick(state,"diagnostics failed")
        raise


if __name__=="__main__":main()
