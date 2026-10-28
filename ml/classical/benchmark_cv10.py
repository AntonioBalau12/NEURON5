"""Single 10-fold classical-model comparison on the shared 70/20/10 split."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import platform
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from threadpoolctl import threadpool_limits

from benchmark import (LABELS, SEED, RSSMonitor, class_weights, load_rows, make_configs,
                       metrics, now_iso, write_json, feature_matrix)
from predictor import PredictionAdapter

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
OUT = BASE / "results_70_20_10_cv10"
OUT.mkdir(parents=True, exist_ok=True)
PROGRESS = BASE / "benchmark_progress_70_20_10_cv10.json"
RESULTS_CSV = BASE / "benchmark_results_70_20_10_cv10.csv"


def status(state, message):
    state["updated_at"] = now_iso()
    state["last_message"] = message
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, PROGRESS)
    eta = state.get("eta_seconds_remaining")
    print(f"[{state['updated_at']}] {message}; completed={state['completed_units']}/{state['planned_units']} "
          f"elapsed={state['elapsed_seconds']:.1f}s ETA={eta if eta is not None else 'uncalibrated'}s "
          f"finish={state.get('projected_finish','?')}", flush=True)


def save_csv(row):
    exists = RESULTS_CSV.exists()
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if not exists: writer.writeheader()
        writer.writerow(row)


def proba(estimator, x):
    raw = estimator.predict_proba(x)
    classes = list(getattr(estimator, "classes_", LABELS))
    aligned = np.zeros((len(raw), len(LABELS)), dtype=np.float64)
    for i, label in enumerate(classes):
        if str(label) in LABELS: aligned[:, LABELS.index(str(label))] = raw[:, i]
    return normalize(aligned, norm="l1", axis=1)


def make_estimator(cfg, y_train, catboost_cls, lightgbm_cls, catboost_device="GPU"):
    weights = class_weights(cfg["weighting"], y_train)
    sample_weights = np.array([weights.get(c, 1.0) for c in y_train], dtype=np.float32) if weights else None
    fam = cfg["family"]
    if fam == "logistic_regression":
        est = LogisticRegression(C=cfg["C"], class_weight="balanced" if cfg["weighting"] == "balanced" else None,
                                 max_iter=2000, random_state=SEED)
        return est, ({"sample_weight": sample_weights} if cfg["weighting"] == "moderate" else {})
    if fam == "linear_svc":
        base = LinearSVC(C=cfg["C"], class_weight="balanced" if cfg["weighting"] == "balanced" else None,
                         random_state=SEED, max_iter=10000)
        return CalibratedClassifierCV(base, cv=3, method="sigmoid"), ({"sample_weight": sample_weights} if cfg["weighting"] == "moderate" else {})
    if fam == "catboost":
        if catboost_cls is None: raise RuntimeError("catboost unavailable")
        return catboost_cls(loss_function="MultiClass", depth=cfg["depth"], iterations=300,
                            learning_rate=0.05, l2_leaf_reg=cfg["l2_leaf_reg"], early_stopping_rounds=30,
                            thread_count=2, random_seed=SEED, verbose=False, allow_writing_files=False,
                            class_weights=[weights.get(c, 1.0) for c in LABELS] if weights else None,
                            eval_metric="MultiClass", task_type=catboost_device,
                            devices="0" if catboost_device == "GPU" else None), {}
    if lightgbm_cls is None: raise RuntimeError("lightgbm unavailable")
    return lightgbm_cls(objective="multiclass", num_class=len(LABELS), num_leaves=cfg["num_leaves"],
                        n_estimators=300, learning_rate=0.05, min_child_samples=20,
                        reg_lambda=cfg["reg_lambda"], n_jobs=2, random_state=SEED,
                        class_weight=weights, verbosity=-1), {}


def fit_one(est, cfg, x_train, y_train, x_valid, y_valid, fit_kw, catboost_device):
    fam = cfg["family"]
    if fam == "catboost":
        est.fit(x_train, y_train, eval_set=(x_valid, y_valid), verbose=False)
    elif fam == "lightgbm":
        from lightgbm import early_stopping, log_evaluation
        est.fit(x_train, y_train, eval_set=[(x_valid, y_valid)],
                callbacks=[early_stopping(30, verbose=False), log_evaluation(0)], **fit_kw)
    else:
        est.fit(x_train, y_train, **fit_kw)
    return est


def main():
    os.environ.update({"OMP_NUM_THREADS":"2", "MKL_NUM_THREADS":"2", "OPENBLAS_NUM_THREADS":"2", "TOKENIZERS_PARALLELISM":"false"})
    start = time.perf_counter(); wall_start = time.time()
    rows, lex = load_rows()
    with (ROOT / "ml/shared/splits.csv").open(encoding="utf-8-sig", newline="") as f:
        split_map = {r["id"]: r["split"] for r in csv.DictReader(f)}
    with (ROOT / "ml/shared/cv10_folds.csv").open(encoding="utf-8-sig", newline="") as f:
        fold_map = {r["id"]: int(r["fold"]) for r in csv.DictReader(f)}
    ids = [r["id"] for r in rows]
    if len(split_map) != len(rows) or set(split_map) != set(ids): raise ValueError("shared split must map each row ID once")
    train = np.array([i for i, rid in enumerate(ids) if split_map[rid] == "train"], dtype=int)
    val = np.array([i for i, rid in enumerate(ids) if split_map[rid] == "validation"], dtype=int)
    test = np.array([i for i, rid in enumerate(ids) if split_map[rid] == "test"], dtype=int)
    folds = np.array([fold_map[ids[i]] for i in train], dtype=int)
    y = np.array([r["label"].strip().lower() for r in rows])
    configs = make_configs()
    units = len(configs) * 10
    family_units = Counter(c["family"] for c in configs)
    state = {"status":"RUNNING", "started_at":now_iso(), "updated_at":now_iso(), "finished_at":None,
             "pid":os.getpid(), "platform":platform.platform(), "protocol":"one benchmark run; shared 70/20/10; grouped 10-fold CV over train only",
             "planned_configurations":len(configs), "planned_units":units, "completed_configurations":0,
             "completed_units":0, "elapsed_seconds":0.0, "eta_seconds_remaining":None,
             "preliminary_eta_seconds_uncalibrated":units * 4, "current_family":None, "current_configuration":None,
             "current_fold":None, "dataset_counts":{"train":len(train),"validation":len(val),"test":len(test)},
             "fold_seconds":[], "family_status":{}}
    state["family_eta_seconds_remaining"]={f:n*10*4 for f,n in family_units.items()}
    status(state, f"startup: planned {len(configs)} configurations / {units} fold-fits; preliminary duration estimate UNCALIBRATED")
    try:
        t = time.perf_counter()
        prepared = {}
        for fold in range(10):
            va = train[folds == fold]; tr = train[folds != fold]
            x, builder = feature_matrix(rows, lex, tr)
            prepared[fold] = {"x":x, "builder":builder, "train":tr, "valid":va,
                              "dense":x.toarray().astype(np.float32, copy=False)}
        prepare_seconds = time.perf_counter() - t
        write_json(OUT / "preparation.json", {"duration_seconds":prepare_seconds,"outer_counts":state["dataset_counts"],
                    "fold_counts":{str(k):int((folds==k).sum()) for k in range(10)},
                    "features":"text + date + lexicon; form excluded from inference features",
                    "split_sha256":__import__('hashlib').sha256((ROOT/'ml/shared/splits.csv').read_bytes()).hexdigest()})
        try:
            from catboost import CatBoostClassifier
        except Exception as exc:
            CatBoostClassifier=None; state["catboost_import_error"]=repr(exc)
        try:
            from lightgbm import LGBMClassifier
        except Exception as exc:
            LGBMClassifier=None; state["lightgbm_import_error"]=repr(exc)
        state["preparation_seconds"] = prepare_seconds
        status(state, f"prepared fold-local features in {prepare_seconds:.1f}s; beginning CV")
        records=[]; fold_durations=[]; durations_by_family=defaultdict(list); family_gpu={}; cv_best={}
        for ci,cfg in enumerate(configs):
            config_start=time.perf_counter(); family=cfg["family"]
            name=f"{family}:{cfg.get('C',cfg.get('depth',cfg.get('num_leaves')))}:{cfg.get('l2_leaf_reg',cfg.get('reg_lambda',''))}:{cfg['weighting']}"
            state["current_family"]=family; state["current_configuration"]=name
            oof=np.zeros((len(rows),len(LABELS)),dtype=np.float64); fold_stats=[]; fit_total=0.0; pred_total=0.0
            for fi in range(10):
                state["current_fold"]=fi; t0=time.perf_counter(); pdata=prepared[fi]
                tr,va=pdata["train"],pdata["valid"]
                use_dense=family=="catboost"; xx=pdata["dense"] if use_dense else pdata["x"]
                estimator,fit_kw=make_estimator(cfg,y[tr],CatBoostClassifier,LGBMClassifier,family_gpu.get(family,"GPU"))
                try:
                    with threadpool_limits(limits=2):
                        fit_one(estimator,cfg,xx[tr],y[tr],xx[va],y[va],fit_kw,family_gpu.get(family,"GPU"))
                except Exception as exc:
                    if family!="catboost" or family_gpu.get(family,"GPU")!="GPU": raise
                    family_gpu[family]="CPU"; state["catboost_gpu_fallback"]=f"{type(exc).__name__}: {exc}"
                    estimator,fit_kw=make_estimator(cfg,y[tr],CatBoostClassifier,LGBMClassifier,"CPU")
                    with threadpool_limits(limits=2): fit_one(estimator,cfg,xx[tr],y[tr],xx[va],y[va],fit_kw,"CPU")
                fit_sec=time.perf_counter()-t0; fit_total+=fit_sec
                tp=time.perf_counter()
                with threadpool_limits(limits=2): probs=proba(estimator,xx[va])
                pred_sec=time.perf_counter()-tp; pred_total+=pred_sec
                oof[va]=probs
                fold_stats.append({"fold":fi,"rows":len(va),"fit_seconds":fit_sec,"predict_seconds":pred_sec,
                                   "macro_f1":metrics(y[va],probs)["macro_f1"]})
                state["completed_units"]+=1; state["elapsed_seconds"]=time.perf_counter()-start
                fold_durations.append(time.perf_counter()-t0)
                state["fold_seconds"].append(fold_durations[-1])
                durations_by_family[family].append(fold_durations[-1])
                median=float(np.median(fold_durations)); remain=units-state["completed_units"]
                state["eta_seconds_remaining"]=median*remain
                state["projected_finish"]=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=state["eta_seconds_remaining"])).isoformat(timespec="seconds")
                state["current_eta_seconds"]=median
                state["current_configuration_eta_seconds"]=float(np.median(durations_by_family[family]))*(9-fi)
                state["current_fold_scores"]=fold_stats
                covered=train[np.isin(folds,np.arange(fi+1))]
                state["current_oof_metrics"]={k:v for k,v in metrics(y[covered],oof[covered]).items() if k not in {"predicted","confidence"}}
                state["family_eta_seconds_remaining"]={fam:max(0,(family_units[fam]*10-sum(len(x["folds"]) for x in records if x["configuration"]["family"]==fam))-(len(fold_stats) if fam==family else 0))*float(np.median(durations_by_family[fam]) if durations_by_family[fam] else median) for fam in family_units}
                status(state,f"finished {name} fold {fi+1}/10; fold={fold_stats[-1]['macro_f1']:.4f}")
            cvm=metrics(y[train],oof[train]); fold_f1=[f["macro_f1"] for f in fold_stats]
            record={"configuration":cfg,"configuration_id":name,"cv_oof":{k:v for k,v in cvm.items() if k not in {"predicted","confidence"}},
                    "fold_macro_f1_mean":float(np.mean(fold_f1)),"fold_macro_f1_std":float(np.std(fold_f1)),
                    "fold_macro_f1_min":float(np.min(fold_f1)),"fold_macro_f1_max":float(np.max(fold_f1)),
                    "folds":fold_stats,"fit_seconds_total":fit_total,"predict_seconds_total":pred_total,
                    "training_hardware":"GPU" if family=="catboost" and family_gpu.get(family,"GPU")=="GPU" else "CPU"}
            records.append(record); write_json(OUT/f"cv_{ci+1:02d}.json",record)
            save_csv({"configuration_id":name,"family":family,"weighting":cfg["weighting"],"C":cfg.get("C"),
                      "depth":cfg.get("depth"),"l2_leaf_reg":cfg.get("l2_leaf_reg"),"num_leaves":cfg.get("num_leaves"),
                      "reg_lambda":cfg.get("reg_lambda"),"cv_accuracy":cvm["accuracy"],"cv_balanced_accuracy":cvm["balanced_accuracy"],
                      "cv_macro_f1":cvm["macro_f1"],"fold_macro_f1_mean":np.mean(fold_f1),"fold_macro_f1_std":np.std(fold_f1),
                      "false_precision":cvm["classes"]["false"]["precision"],"false_recall":cvm["classes"]["false"]["recall"],
                      "false_f1":cvm["classes"]["false"]["f1"],"false_support":cvm["classes"]["false"]["support"],
                      "unsure_precision":cvm["classes"]["unsure"]["precision"],"unsure_recall":cvm["classes"]["unsure"]["recall"],
                      "unsure_f1":cvm["classes"]["unsure"]["f1"],"unsure_support":cvm["classes"]["unsure"]["support"],
                      "ece_10bin":cvm["ece_10bin"],"multiclass_brier":cvm["multiclass_brier"],
                      "fit_seconds_total":fit_total,"training_hardware":record["training_hardware"],"state":"completed"})
            state["completed_configurations"]+=1
            old=cv_best.get(family)
            score=(cvm["macro_f1"],cvm["balanced_accuracy"])
            if old is None or score>old[0]: cv_best[family]=(score,cfg,ci+1)
            state["family_status"][family]={"configurations_completed":sum(r["configuration"]["family"]==family for r in records),
                                              "best_cv_macro_f1":cv_best[family][0][0]}
            status(state,f"completed CV configuration {ci+1}/{len(configs)} {name}; pooled OOF macro-F1={cvm['macro_f1']:.4f}")

        # Refit one CV-selected candidate per family. Validation chooses the family;
        # the outer test is kept for the final selected model only.
        family_valid=[]; finalists={}
        for family,(score,cfg,idx) in cv_best.items():
            tr=train; estimator,fit_kw=make_estimator(cfg,y[tr],CatBoostClassifier,LGBMClassifier,family_gpu.get(family,"GPU"))
            use_dense=family=="catboost"; xval,builder=feature_matrix(rows,lex,tr); x_dense=xval.toarray().astype(np.float32,copy=False) if use_dense else None
            xx=x_dense if use_dense else xval
            mon=RSSMonitor(); mon.start(); fit_start=time.perf_counter()
            with threadpool_limits(limits=2): fit_one(estimator,cfg,xx[tr],y[tr],xx[val],y[val],fit_kw,family_gpu.get(family,"GPU"))
            fit_sec=time.perf_counter()-fit_start; mon.stop()
            vp=proba(estimator,xx[val]); vm=metrics(y[val],vp)
            fam_dir=OUT/"family_candidates"/family; fam_dir.mkdir(parents=True,exist_ok=True)
            ser=time.perf_counter()
            native=None
            if family=="catboost":
                native=fam_dir/"model.cbm"; estimator.save_model(str(native))
                from catboost import CatBoostClassifier as CB
                infer_est=CB(task_type="CPU",thread_count=2,verbose=False); infer_est.load_model(str(native))
            else: infer_est=estimator
            model_path=fam_dir/"adapter.joblib"
            joblib.dump(PredictionAdapter(infer_est,{k:v for k,v in builder.items() if k not in {"char_matrix","info"}},tuple(LABELS),family),model_path,compress=3)
            model_size=model_path.stat().st_size+(native.stat().st_size if native else 0); serialize_sec=time.perf_counter()-ser
            finalists[family]={"configuration_id":records[idx-1]["configuration_id"],"configuration":cfg,
                               "validation":{k:v for k,v in vm.items() if k not in {"predicted","confidence"}},
                               "fit_seconds":fit_sec,"serialize_seconds":serialize_sec,"model_size_bytes":model_size,
                               "peak_rss_mb":mon.peak,"artifact":str(model_path.relative_to(ROOT))}
            family_valid.append((vm["macro_f1"],vm["balanced_accuracy"],family,cfg))
        winner=sorted(family_valid,reverse=True)[0]
        selected_family,selected_cfg=winner[2],winner[3]
        final_train=np.concatenate([train,val]); final_est,final_kw=make_estimator(selected_cfg,y[final_train],CatBoostClassifier,LGBMClassifier,family_gpu.get(selected_family,"GPU"))
        xt,builder=feature_matrix(rows,lex,final_train); dense=xt.toarray().astype(np.float32,copy=False) if selected_family=="catboost" else None
        xfit=dense if selected_family=="catboost" else xt
        mon=RSSMonitor(); mon.start(); final_t=time.perf_counter()
        # Do not use outer-test labels as a boosting early-stopping set.
        with threadpool_limits(limits=2): final_est.fit(xfit[final_train],y[final_train],**final_kw)
        final_fit=time.perf_counter()-final_t; mon.stop()
        tser=time.perf_counter(); final_dir=OUT/"selected_model"; final_dir.mkdir(parents=True,exist_ok=True)
        native=None
        if selected_family=="catboost":
            native=final_dir/"model.cbm"; final_est.save_model(str(native))
            from catboost import CatBoostClassifier as CB
            cpu_est=CB(task_type="CPU",thread_count=2,verbose=False); cpu_est.load_model(str(native))
        else: cpu_est=final_est
        final_path=final_dir/"adapter.joblib"
        joblib.dump(PredictionAdapter(cpu_est,{k:v for k,v in builder.items() if k not in {"char_matrix","info"}},tuple(LABELS),selected_family),final_path,compress=3)
        final_size=final_path.stat().st_size+(native.stat().st_size if native else 0); serialize_sec=time.perf_counter()-tser
        final_adapter=joblib.load(final_path); test_rows=[rows[int(i)] for i in test]
        # Measure the full adapter path, including text/date feature extraction.
        with threadpool_limits(limits=2):
            test_prob=final_adapter.predict_proba(test_rows)
            test_metrics=metrics(y[test],test_prob)
            reps=max(3,int(5000/max(1,len(test))))
            speed_start=time.perf_counter()
            for _ in range(reps): final_adapter.predict_proba(test_rows)
            speed_sec=time.perf_counter()-speed_start
        report={"status":"completed","generated_at":now_iso(),"started_at":state["started_at"],"elapsed_seconds":time.perf_counter()-start,
                "split":{"train":len(train),"validation":len(val),"test":len(test),"cv_folds":10},
                "preparation_seconds":prepare_seconds,"configuration_count":len(configs),"fold_fit_count":units,
                "cv_ranking":[{"family":family,"configuration_id":records[idx-1]["configuration_id"],"cv_macro_f1":score[0],"cv_balanced_accuracy":score[1],
                                "validation_macro_f1":v[0],"validation_balanced_accuracy":v[1]} for family,(score,cfg,idx) in cv_best.items()
                               for v in [next((q[0:2] for q in family_valid if q[2]==family),(None,None))]],
                "family_candidates":finalists,"selected":{"family":selected_family,"configuration":selected_cfg,
                    "cv_macro_f1":cv_best[selected_family][0][0],"validation_macro_f1":winner[0],"validation_balanced_accuracy":winner[1],
                    "test_metrics":{k:v for k,v in test_metrics.items() if k not in {"predicted","confidence"}},
                    "test_predict_seconds_one_batch":speed_sec/reps,"cpu_inference_rows_per_second":len(test)*reps/speed_sec,
                    "cpu_inference_seconds_per_20000_rows":20000/(len(test)*reps/speed_sec),"repeated_batches":reps,
                    "fit_seconds_train_plus_validation":final_fit,"serialization_seconds":serialize_sec,"model_size_bytes":final_size,
                    "peak_rss_mb":mon.peak,"artifact":str(final_path.relative_to(ROOT))},
                "metrics":"accuracy, balanced accuracy, macro-F1, per-class precision/recall/F1/support, confusion matrix, ECE, multiclass Brier",
                "cv_results_csv":str(RESULTS_CSV.relative_to(ROOT)),"limitations":["subject/attribute histories can cross partitions; see shared splitting_audit.json",
                    "UNSURE support is small; report its support with every score","validation selects family; outer test is scored only for the selected model"]}
        write_json(OUT/"summary.json",report)
        state.update({"status":"COMPLETED","finished_at":now_iso(),"projected_finish":now_iso(),"elapsed_seconds":time.perf_counter()-start,
                      "eta_seconds_remaining":0,"current_family":None,"current_configuration":None,"current_fold":None,
                      "selected_family":selected_family,"selected_configuration":selected_cfg})
        status(state,f"completed one benchmark run; selected {selected_family} with test macro-F1={test_metrics['macro_f1']:.4f}")
        return 0
    except Exception as exc:
        state.update({"status":"FAILED","finished_at":now_iso(),"error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc(),"elapsed_seconds":time.perf_counter()-start})
        status(state,"benchmark failed")
        raise


if __name__=="__main__": raise SystemExit(main())
