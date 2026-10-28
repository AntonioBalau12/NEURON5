"""One isolated GPU CatBoost pilot; never reads outer-test records."""
from __future__ import annotations
import csv, json, os, time, traceback
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from catboost import CatBoostClassifier
from benchmark import LABELS, SEED, feature_matrix, metrics, now_iso

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"results_weight_diagnostics_70_20_10"

def main():
    started=time.perf_counter(); split_path=ROOT/"ml/shared/splits.csv"
    with split_path.open(encoding="utf-8-sig",newline="") as f: split={r["id"]:r["split"] for r in csv.DictReader(f)}
    rows=[]
    with (ROOT/"data/practice.csv").open(encoding="utf-8-sig",newline="") as f:
        for raw in csv.DictReader(f):
            part=split.get(raw["id"])
            if part not in {"train","validation"}: continue
            row={"id":raw["id"],"text":raw["text"],"date":raw["date"],"label":raw["label"].strip().lower(),"split":part}
            rows.append(row)
    with (ROOT/"data/lexicon.json").open(encoding="utf-8") as f: lex=json.load(f)
    train=np.array([i for i,r in enumerate(rows) if r["split"]=="train"])
    val=np.array([i for i,r in enumerate(rows) if r["split"]=="validation"])
    y=np.asarray([r["label"] for r in rows]); feature_rows=[{k:r[k] for k in ("id","text","date")} for r in rows]
    t=time.perf_counter(); x,builder=feature_matrix(feature_rows,lex,train); prep=time.perf_counter()-t
    dense=x.toarray().astype(np.float32)
    model=CatBoostClassifier(loss_function="MultiClass",depth=5,iterations=300,learning_rate=.05,l2_leaf_reg=3,
        thread_count=2,random_seed=SEED,verbose=False,allow_writing_files=False,class_weights=[2.0,1.0,1.0],
        task_type="GPU",devices="0")
    result={"status":"RUNNING","started_at":now_iso(),"protocol":"GPU fit on train only; validation scored after fit; outer test skipped",
            "gpu":"NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB VRAM","weights_true_false_unsure":[1.0,2.0,1.0],
            "preparation_seconds":prep,"train_rows":len(train),"validation_rows":len(val),"outer_test":"not loaded"}
    try:
        t=time.perf_counter()
        with threadpool_limits(limits=2): model.fit(dense[train],y[train])
        result["gpu_fit_seconds"]=time.perf_counter()-t
        path=OUT/"catboost_gpu_pilot.cbm"; model.save_model(str(path)); result["native_model_size_bytes"]=path.stat().st_size
        # Load CPU-native inference model and measure runtime compatibility/throughput.
        cpu=CatBoostClassifier(task_type="CPU",thread_count=2,verbose=False);cpu.load_model(str(path))
        t=time.perf_counter()
        with threadpool_limits(limits=2): raw=cpu.predict_proba(dense[val])
        result["cpu_validation_inference_seconds"]=time.perf_counter()-t
        result["cpu_validation_rows_per_second"]=len(val)/max(result["cpu_validation_inference_seconds"],1e-9)
        probs=np.zeros((len(val),3))
        for j,c in enumerate(cpu.classes_):probs[:,LABELS.index(str(c))]=raw[:,j]
        result["validation_metrics"]={k:v for k,v in metrics(y[val],probs).items() if k not in {"predicted","confidence"}}
        result["validation_predictions"]=[{"row_id":rows[int(i)]["id"],"true_label":str(y[i]),"predicted_label":str(LABELS[int(np.argmax(probs[j]))]),
            "probability_true":float(probs[j,LABELS.index("true")]),"probability_false":float(probs[j,LABELS.index("false")]),
            "probability_unsure":float(probs[j,LABELS.index("unsure")])} for j,i in enumerate(val)]
        result["status"]="COMPLETED"
    except Exception as exc:
        result.update({"status":"FAILED","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
    result["finished_at"]=now_iso();result["elapsed_seconds"]=time.perf_counter()-started
    (OUT/"catboost_gpu_pilot.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="validation_predictions"},indent=2),flush=True)

if __name__=="__main__":main()
