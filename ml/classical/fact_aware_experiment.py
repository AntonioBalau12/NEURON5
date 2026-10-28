"""Run grouped OOF, validation, and frozen outer-test feature ablations."""
from __future__ import annotations

import csv, datetime as dt, json, os, platform, time, traceback
from collections import Counter
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib
import numpy as np
import psutil
from scipy.sparse import csr_matrix, hstack
from threadpoolctl import threadpool_limits

from core.graph import build_graph
from foundation import Lexicon
from benchmark import (LABELS, SEED, load_rows, load_shared_splits, make_feature_builder,
                       transform_features, metrics, now_iso, write_json)
from fact_aware_features import FEATURE_NAMES, FactAwareFeatureExtractor

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
OUT = BASE / "results_fact_aware_70_20_10"
OUT.mkdir(parents=True, exist_ok=True)
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
SPLIT_NAMES = ("A_text_baseline", "B_text_parser", "C_text_parser_graph", "D_graph_only")
WEIGHTS = {"false": 3.0, "true": 1.0, "unsure": 3.0}  # Existing LightGBM CV Macro-F1 leader.
PROCESS = psutil.Process(os.getpid())


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if not rows: return
    if fields is None:
        fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def append_live(row):
    path=OUT/"live_completed_units.csv"
    fields=list(dict.fromkeys(row.keys()))
    exists=path.exists()
    if exists:
        with path.open(encoding="utf-8",newline="") as f: fields=list(csv.DictReader(f).fieldnames or fields)
    with path.open("a",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        if not exists:w.writeheader()
        w.writerow(row)


def compact_metrics(y, probs):
    value=metrics(np.asarray(y),np.asarray(probs))
    value.pop("predicted",None);value.pop("confidence",None)
    return value


def load_manifests(rows):
    splits, audit = load_shared_splits(rows)
    with (ROOT / "ml/shared/cv10_folds.csv").open(encoding="utf-8-sig", newline="") as f:
        folds = {r["id"]: int(r["fold"]) for r in csv.DictReader(f)}
    train_ids = {r["id"] for r in rows if splits[r["id"]] == "train"}
    if set(folds) != train_ids: raise ValueError("cv10_folds.csv must map every train ID exactly once")
    return splits, folds, audit


def truth_row(r):
    # Reference evidence gets labels/forms only for training rows. Never call for val/test rows.
    return {"id": r["id"], "text": r["text"], "date": r["date"], "label": r["label"], "form": r.get("form", "")}


def runtime_row(r):
    # Exact inference-time surface: deliberately omit practice label and form.
    return {"id": r["id"], "text": r["text"], "date": r["date"]}


def graph_from_references(reference_rows, lexicon):
    # No evaluation/target rows enter the graph. Forms and labels are provided only
    # for rows in this fold's allowed reference-training partition.
    return build_graph([], lexicon, [truth_row(r) for r in reference_rows])


def extract_rows(target_rows, graph, lexicon):
    extractor = FactAwareFeatureExtractor(lexicon, graph)
    matrix, details = [], []
    for r in target_rows:
        values, info = extractor.transform(r["text"], r["date"], r["id"])
        matrix.append([values[name] for name in FEATURE_NAMES])
        details.append({"row_id": r["id"], **info, "feature_values": values})
    return csr_matrix(np.asarray(matrix, dtype=np.float32)), details


def graph_features(target_rows, reference_rows, lexicon):
    graph = graph_from_references(reference_rows, lexicon)
    matrix, details = extract_rows(target_rows, graph, lexicon)
    return matrix, details, graph


def make_x(base_x, parser_x, graph_x, family):
    if family == SPLIT_NAMES[0]: return base_x
    if family == SPLIT_NAMES[1]: return hstack([base_x, parser_x], format="csr", dtype=np.float32)
    if family == SPLIT_NAMES[2]: return hstack([base_x, parser_x, graph_x], format="csr", dtype=np.float32)
    return graph_x


def new_model(lgbm):
    return lgbm(objective="multiclass", num_class=3, num_leaves=15, n_estimators=300,
                learning_rate=0.05, min_child_samples=20, reg_lambda=1, n_jobs=2,
                random_state=SEED, class_weight=WEIGHTS, verbosity=-1)


def pred_rows(ids, y, probs, model, part, fold=None):
    pred = np.asarray(LABELS)[np.argmax(probs, axis=1)]
    return [{"row_id": ids[i], "true_label": y[i], "predicted_label": str(pred[i]),
             "probability_true": float(probs[i, LABELS.index("true")]),
             "probability_false": float(probs[i, LABELS.index("false")]),
             "probability_unsure": float(probs[i, LABELS.index("unsure")]),
             "model_configuration": model, "fold_or_split": f"fold_{fold}" if fold is not None else part}
            for i in range(len(ids))]


def progress(state, message, unit_elapsed=None):
    state["updated_at"] = now_iso(); state["message"] = message
    state["elapsed_seconds"] = round(time.perf_counter() - state["clock"], 2)
    if unit_elapsed is not None:
        state["unit_seconds"].append(unit_elapsed)
    remaining = state["planned_units"] - state["completed_units"]
    sample = float(np.median(state["unit_seconds"])) if state["unit_seconds"] else 8.0
    prep_sample = float(np.median(state["fold_preparation_seconds"])) if state["fold_preparation_seconds"] else 30.0
    remaining_fold_prep = max(0, state["planned_cv_folds"] - state["completed_cv_folds"]) * prep_sample
    final_prep = 0.0 if state["final_preparation_complete"] else prep_sample
    state["eta_seconds_remaining"] = round(remaining * sample + remaining_fold_prep + final_prep, 2)
    state["projected_finish_utc"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=state["eta_seconds_remaining"])).isoformat(timespec="seconds")
    saved = {k:v for k,v in state.items() if k != "clock"}
    write_json(OUT / "progress.json", saved)
    print(f"[{state['updated_at']}] {message} | {state['completed_units']}/{state['planned_units']} | elapsed={state['elapsed_seconds']}s ETA={state['eta_seconds_remaining']}s finish={state['projected_finish_utc']}", flush=True)


def run():
    os.environ.update({"OMP_NUM_THREADS":"2", "MKL_NUM_THREADS":"2", "OPENBLAS_NUM_THREADS":"2", "TOKENIZERS_PARALLELISM":"false"})
    import lightgbm
    started_wall = time.time(); clock = time.perf_counter()
    all_rows, rawlex = load_rows()
    # Materialize test target forms only as opaque values before selecting rows; never pass them to graph/feature code.
    split_map, fold_map, split_audit = load_manifests(all_rows)
    lexicon, lex_issues = Lexicon.parse(rawlex)
    if lexicon is None: raise ValueError("invalid lexicon: " + "; ".join(lex_issues))
    rows_by_split = {s:[r for r in all_rows if split_map[r["id"]] == s] for s in ("train","validation","test")}
    ytrain = np.array([r["label"] for r in rows_by_split["train"]]); yval = np.array([r["label"] for r in rows_by_split["validation"]]); ytest = np.array([r["label"] for r in rows_by_split["test"]])
    folds = sorted(set(fold_map.values()))
    planned = len(folds) * len(SPLIT_NAMES) + len(SPLIT_NAMES)
    state = {"status":"RUNNING", "started_at":dt.datetime.fromtimestamp(started_wall,dt.timezone.utc).isoformat(timespec="seconds"),
             "updated_at":now_iso(), "phase":"feature_preparation", "planned_units":planned, "completed_units":0,
             "planned_configurations":planned, "preliminary_duration_seconds_uncalibrated":planned*8,
             "unit_seconds":[], "fold_preparation_seconds":[], "planned_cv_folds":len(folds), "completed_cv_folds":0,
             "final_preparation_complete":False, "clock":clock, "dataset_rows":{"train":len(ytrain),"validation":len(yval),"test":len(ytest)},
             "split_manifest":"ml/shared/splits.csv", "cv_manifest":"ml/shared/cv10_folds.csv", "thread_limit":2,
             "model":"LightGBM leaves=15, n_estimators=300, reg_lambda=1, class_weights=true:false:unsure=1:3:3"}
    write_json(OUT / "progress.json", {k:v for k,v in state.items() if k != "clock"})
    print(f"Planned {planned} fits; preliminary ETA {planned*8}s (uncalibrated).", flush=True)
    idindex = {r["id"]:i for i,r in enumerate(all_rows)}
    oof = {name:[] for name in SPLIT_NAMES}; timing=[]; feature_reports=[]
    # Grouped 10-fold out-of-fold evaluation over the fixed training partition.
    for fold in folds:
        fold_prep_start=time.perf_counter()
        targets = [r for r in rows_by_split["train"] if fold_map[r["id"]] == fold]
        references = [r for r in rows_by_split["train"] if fold_map[r["id"]] != fold]
        train_index = np.array([idindex[r["id"]] for r in references]); target_index = np.array([idindex[r["id"]] for r in targets])
        t0=time.perf_counter(); base_x,builder=transform_features(all_rows, make_feature_builder(references,rawlex)); feature_sec=time.perf_counter()-t0
        t0=time.perf_counter(); graph=graph_from_references(references,lexicon)
        graph_x,details=extract_rows(targets,graph,lexicon); graph_sec=time.perf_counter()-t0
        parser_x = csr_matrix(np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES[:6]] for d in details], dtype=np.float32))
        # parser B uses its six parser-only columns; graph C adds all graph columns.
        all_feature = csr_matrix(np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES] for d in details],dtype=np.float32))
        parser_only = csr_matrix(np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES[:6]] for d in details],dtype=np.float32))
        # Compute parser-only for reference rows from text with a graph built only from this fold's training references.
        ref_graph_x, ref_details = extract_rows(references, graph, lexicon)
        ref_all = np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES] for d in ref_details],dtype=np.float32)
        ref_parser = csr_matrix(ref_all[:,:6])
        ref_graph = csr_matrix(ref_all)
        state["fold_preparation_seconds"].append(time.perf_counter()-fold_prep_start)
        train_base = base_x[train_index]; target_base=base_x[target_index]
        ytr=np.array([r["label"] for r in references]); ytarget=np.array([r["label"] for r in targets])
        for name in SPLIT_NAMES:
            unit=time.perf_counter(); mem_before=PROCESS.memory_info().rss/1024**2
            xtr=make_x(train_base,ref_parser,ref_graph,name)
            xva=make_x(target_base,parser_only,all_feature,name)
            model=new_model(lightgbm.LGBMClassifier)
            with threadpool_limits(limits=2): model.fit(xtr,ytr)
            train_sec=time.perf_counter()-unit
            inf=time.perf_counter()
            with threadpool_limits(limits=2): probs=model.predict_proba(xva)
            infer_sec=time.perf_counter()-inf
            # Align output class columns to stable labels.
            aligned=np.zeros((len(targets),3),dtype=float)
            for j,c in enumerate(model.classes_): aligned[:,LABELS.index(str(c))]=probs[:,j]
            oof[name].extend(pred_rows([r["id"] for r in targets],ytarget,aligned,name,"train_oof",fold))
            timing.append({"model_configuration":name,"phase":"cv_oof","fold":fold,"feature_extraction_seconds":round(feature_sec+graph_sec,4),"training_seconds":round(train_sec,4),"inference_seconds":round(infer_sec,4),"rows_per_second":round(len(targets)/infer_sec,2) if infer_sec else None,"peak_rss_mb":round(max(mem_before,PROCESS.memory_info().rss/1024**2),1),"n_features":int(xtr.shape[1]),"graph_index_facts":sum(map(len,graph.facts_by_subject_attribute.values()))})
            append_live({"model_configuration":name,"phase":"cv_oof","fold":fold,"rows":len(targets),"training_seconds":round(train_sec,4),"inference_seconds":round(infer_sec,4),"rows_per_second":round(len(targets)/infer_sec,2) if infer_sec else None,"peak_rss_mb":round(max(mem_before,PROCESS.memory_info().rss/1024**2),1),**compact_metrics(ytarget,aligned)})
            state["completed_units"]+=1; progress(state,f"CV fold {fold} {name} complete",time.perf_counter()-unit)
        state["completed_cv_folds"] += 1
        for d in details:
            vals=d["feature_values"]
            feature_reports.append({"row_id":d["row_id"],"split":"train_oof","fold":fold,"parsed_fact_count":vals["parsed_fact_count"],"parser_coverage":vals["parse_coverage"],"graph_evidence_available":vals["evidence_available"],"retrieved_evidence_count":len(d["retrieved_evidence"])})
    # OOF metric export. Each train row must occur once/configuration.
    oof_metrics=[]
    for name, rows in oof.items():
        write_csv(OUT / f"{name}_oof_predictions.csv", rows)
        if len(rows) != len(rows_by_split["train"]): raise ValueError(f"OOF rows mismatch for {name}: {len(rows)}")
        oof_metrics.append({"model_configuration":name,"phase":"cv_oof",**metrics(np.array([r["true_label"] for r in rows]),np.array([[r["probability_false"],r["probability_true"],r["probability_unsure"]] for r in rows]))})
    # Train-only graph features for validation and untouched test, built separately with runtime-shaped rows.
    references=rows_by_split["train"]
    t0=time.perf_counter(); text_builder=make_feature_builder(references,rawlex); base_x,_=transform_features(all_rows,text_builder); textprep=time.perf_counter()-t0
    train_graph=graph_from_references(references,lexicon)
    val_x,val_details=extract_rows(rows_by_split["validation"],train_graph,lexicon)
    test_x,test_details=extract_rows(rows_by_split["test"],train_graph,lexicon)
    train_x,train_details=extract_rows(references,train_graph,lexicon)
    state["final_preparation_complete"] = True
    trainvals=np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES] for d in train_details],dtype=np.float32)
    valvals=np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES] for d in val_details],dtype=np.float32)
    testvals=np.asarray([[d["feature_values"][k] for k in FEATURE_NAMES] for d in test_details],dtype=np.float32)
    fit_indices=np.array([idindex[r["id"]] for r in references]); vi=np.array([idindex[r["id"]] for r in rows_by_split["validation"]]); ti=np.array([idindex[r["id"]] for r in rows_by_split["test"]])
    validation_predictions=[]; test_predictions=[]; models={}
    for name in SPLIT_NAMES:
        unit=time.perf_counter(); mem_before=PROCESS.memory_info().rss/1024**2
        parser_tr=csr_matrix(trainvals[:,:6]); graph_tr=csr_matrix(trainvals)
        parser_va=csr_matrix(valvals[:,:6]); graph_va=csr_matrix(valvals)
        parser_te=csr_matrix(testvals[:,:6]); graph_te=csr_matrix(testvals)
        xtr=make_x(base_x[fit_indices],parser_tr,graph_tr,name); xval=make_x(base_x[vi],parser_va,graph_va,name); xtest=make_x(base_x[ti],parser_te,graph_te,name)
        model=new_model(lightgbm.LGBMClassifier)
        tfit=time.perf_counter()
        with threadpool_limits(limits=2): model.fit(xtr,ytrain)
        fitsec=time.perf_counter()-tfit
        ti0=time.perf_counter()
        with threadpool_limits(limits=2): pval=model.predict_proba(xval)
        valsec=time.perf_counter()-ti0
        aligned_val=np.zeros((len(pval),3))
        for j,c in enumerate(model.classes_):aligned_val[:,LABELS.index(str(c))]=pval[:,j]
        validation_predictions.extend(pred_rows([r["id"] for r in rows_by_split["validation"]],yval,aligned_val,name,"validation"))
        # Freeze validation-derived decision: all configs evaluated with standard argmax.
        ti0=time.perf_counter()
        with threadpool_limits(limits=2): ptest=model.predict_proba(xtest)
        testsec=time.perf_counter()-ti0
        aligned_test=np.zeros((len(ptest),3))
        for j,c in enumerate(model.classes_):aligned_test[:,LABELS.index(str(c))]=ptest[:,j]
        test_predictions.extend(pred_rows([r["id"] for r in rows_by_split["test"]],ytest,aligned_test,name,"test"))
        # Keep each train-only trained candidate for diagnostics/integration review.
        model_file=OUT / "models" / f"{name}.joblib"; model_file.parent.mkdir(parents=True,exist_ok=True)
        serial=time.perf_counter(); joblib.dump({"model":model,"feature_configuration":name,"class_weights":WEIGHTS,"labels":LABELS,"feature_names":FEATURE_NAMES,"text_builder":text_builder,"lexicon":rawlex,"graph":None,"note":"Model weights and text vectorizers only; graph evidence must be rebuilt from permitted training rows at inference."},model_file,compress=3); serialsec=time.perf_counter()-serial
        models[name]=model_file.stat().st_size
        timing.append({"model_configuration":name,"phase":"validation_and_test_refit","feature_extraction_seconds":round(textprep,4),"training_seconds":round(fitsec,4),"validation_inference_seconds":round(valsec,4),"test_inference_seconds":round(testsec,4),"serialization_seconds":round(serialsec,4),"serialized_model_bytes":models[name],"validation_rows_per_second":round(len(yval)/valsec,2) if valsec else None,"test_rows_per_second":round(len(ytest)/testsec,2) if testsec else None,"peak_rss_mb":round(max(mem_before,PROCESS.memory_info().rss/1024**2),1),"n_features":int(xtr.shape[1])})
        append_live({"model_configuration":name,"phase":"validation","rows":len(yval),"training_seconds":round(fitsec,4),"inference_seconds":round(valsec,4),"rows_per_second":round(len(yval)/valsec,2) if valsec else None,"peak_rss_mb":round(max(mem_before,PROCESS.memory_info().rss/1024**2),1),**compact_metrics(yval,aligned_val)})
        append_live({"model_configuration":name,"phase":"test","rows":len(ytest),"training_seconds":round(fitsec,4),"inference_seconds":round(testsec,4),"rows_per_second":round(len(ytest)/testsec,2) if testsec else None,"peak_rss_mb":round(max(mem_before,PROCESS.memory_info().rss/1024**2),1),**compact_metrics(ytest,aligned_test)})
        state["completed_units"]+=1; progress(state,f"Validation/test refit {name} complete",time.perf_counter()-unit)
    write_csv(OUT / "validation_predictions.csv",validation_predictions)
    write_csv(OUT / "test_predictions.csv",test_predictions)
    result_rows=[]
    for phase, predictions in (("cv_oof",oof_metrics),("validation",validation_predictions),("test",test_predictions)):
        if phase=="cv_oof": result_rows.extend(predictions); continue
        for name in SPLIT_NAMES:
            subset=[r for r in predictions if r["model_configuration"]==name]
            proba=np.array([[r["probability_false"],r["probability_true"],r["probability_unsure"]] for r in subset])
            result_rows.append({"model_configuration":name,"phase":phase,**metrics(np.array([r["true_label"] for r in subset]),proba)})
    # Store nested metrics as JSON lines-compatible CSV cells.
    write_csv(OUT / "ablation_metrics.csv",[{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in row.items()} for row in result_rows])
    write_csv(OUT / "timings.csv",timing)
    write_csv(OUT / "feature_coverage.csv",feature_reports)
    coverage={}
    for split, details in (("validation",val_details),("test",test_details)):
        coverage[split]={"rows":len(details),"parser_rows_with_fact":sum(bool(d["parsed_facts"]) for d in details),"parser_row_coverage":sum(bool(d["parsed_facts"]) for d in details)/max(1,len(details)),"mean_parse_coverage":float(np.mean([d["feature_values"]["parse_coverage"] for d in details])),"rows_with_graph_evidence":sum(d["feature_values"]["evidence_available"]>0 for d in details),"graph_row_coverage":sum(d["feature_values"]["evidence_available"]>0 for d in details)/max(1,len(details))}
    write_json(OUT / "coverage_summary.json",coverage)
    # Error diagnostics include all categories and representative rows; forms are joined only after predictions.
    base_val={r["row_id"]:r for r in validation_predictions if r["model_configuration"]==SPLIT_NAMES[0]}
    hybrid_val={r["row_id"]:r for r in validation_predictions if r["model_configuration"]==SPLIT_NAMES[2]}
    details_by_id={d["row_id"]:d for d in val_details}; source_by_id={r["id"]:r for r in rows_by_split["validation"]}
    errors=[]
    for rid,b in base_val.items():
        h=hybrid_val[rid]; source=source_by_id[rid]; detail=details_by_id[rid]
        errors.append({"row_id":rid,"text":source["text"],"date":source["date"],"gold_label":b["true_label"],"parsed_facts":json.dumps(detail["parsed_facts"],ensure_ascii=False),"retrieved_evidence":json.dumps(detail["retrieved_evidence"],ensure_ascii=False),"feature_values":json.dumps(detail["feature_values"],ensure_ascii=False),"baseline_prediction":b["predicted_label"],"hybrid_prediction":h["predicted_label"],"baseline_correct":b["predicted_label"]==b["true_label"],"hybrid_correct":h["predicted_label"]==h["true_label"],"form_for_post_prediction_review":source.get("form","")})
    write_csv(OUT / "validation_error_analysis.csv",errors)
    representative=[]
    buckets={"baseline_and_hybrid_correct":lambda e:e["baseline_correct"] and e["hybrid_correct"],"baseline_wrong_hybrid_correct":lambda e:not e["baseline_correct"] and e["hybrid_correct"],"baseline_correct_hybrid_wrong":lambda e:e["baseline_correct"] and not e["hybrid_correct"],"both_wrong":lambda e:not e["baseline_correct"] and not e["hybrid_correct"]}
    for bucket, test in buckets.items():
        for row in [e for e in errors if test(e)][:8]: representative.append({**row,"review_bucket":bucket})
    # Add low/no evidence and parser failure examples if not already present.
    seen={r["row_id"] for r in representative}
    for d in val_details:
        if d["row_id"] in seen:continue
        if not d["parsed_facts"] or d["feature_values"]["evidence_available"]==0 or d["feature_values"]["date_difference_days"]==d["feature_values"]["date_difference_days"]:
            e=next(x for x in errors if x["row_id"]==d["row_id"]); representative.append({**e,"review_bucket":"parser_failure_missing_or_temporal_evidence"});seen.add(d["row_id"])
        if len(representative)>=30:break
    write_csv(OUT / "representative_error_review.csv",representative)
    # Leakage audit and exact split counts; all model inputs above use runtime-shaped target rows.
    report={"started_at":state["started_at"],"finished_at":now_iso(),"elapsed_seconds":round(time.perf_counter()-clock,2),"python":platform.python_version(),"lightgbm":lightgbm.__version__,"dataset_counts":state["dataset_rows"],"label_counts":{"train":dict(Counter(ytrain)),"validation":dict(Counter(yval)),"test":dict(Counter(ytest))},"split_audit":split_audit,"weights_true_false_unsure":[1,3,3],"model_config":{"family":"LightGBM","num_leaves":15,"n_estimators":300,"learning_rate":0.05,"min_child_samples":20,"reg_lambda":1,"n_jobs":2,"random_state":42,"weights_order":"true,false,unsure"},"feature_names":list(FEATURE_NAMES),"validation_test_coverage":coverage,"previous_macro_f1_reference":0.3674,"target_form_inference_usage":False,"validation_test_evidence_usage":"Only text/date/id supplied to feature construction; labels/forms used after predictions for metrics and error review.","test_used_for_selection":False,"graph_branch":"origin/feat/p1-temporal-graph; copied unchanged core/graph modules","limitations":["Graph has no VERIFIED_REFUTATION producer in inspected implementation; false-row forms remain unverified candidates, so measured verified_refutation_count is not evidence of negative truth.","Graph does not infer temporal state from observation dates; mutable fact features use exact observation dates or explicit intervals only.","Event-like attributes are identified by attribute-name heuristic for candidate comparison; value mismatch remains a numeric feature and never becomes a false label.","Parser is deterministic and partial; no NLI or fine-tuned NLP model used.","Broad entity-attribute histories cross folds per existing audit; exact/near duplicates and form signatures were grouped, but semantically related histories may occur in separate folds."],"artifact_sizes_bytes":models}
    write_json(OUT/"run_report.json",report)
    state["status"]="COMPLETED";state["phase"]="complete";state["finished_at"]=now_iso();state["eta_seconds_remaining"]=0;state["elapsed_seconds"]=round(time.perf_counter()-clock,2);write_json(OUT/"progress.json",{k:v for k,v in state.items() if k!="clock"})
    print(f"Completed in {state['elapsed_seconds']}s; results: {OUT}",flush=True)
    print(json.dumps({"metrics":result_rows,"coverage":coverage},indent=2),flush=True)
    return 0


if __name__ == "__main__":
    try:
        with threadpool_limits(limits=2): raise SystemExit(run())
    except Exception as exc:
        write_json(OUT/"failure.json",{"updated_at":now_iso(),"error":repr(exc),"traceback":traceback.format_exc()})
        raise
