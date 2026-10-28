"""Measure end-to-end CPU adapter throughput for the saved GPU-trained model."""
import csv,json,time
from pathlib import Path
import numpy as np
import joblib
from catboost import CatBoostClassifier
from threadpoolctl import threadpool_limits
from benchmark import feature_matrix
from predictor import PredictionAdapter

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent/"results_weight_diagnostics_70_20_10"
with (ROOT/"ml/shared/splits.csv").open(encoding="utf-8-sig",newline="") as f: split={r["id"]:r["split"] for r in csv.DictReader(f)}
rows=[]
with (ROOT/"data/practice.csv").open(encoding="utf-8-sig",newline="") as f:
    for raw in csv.DictReader(f):
        if split.get(raw["id"]) not in {"train","validation"}:continue
        rows.append({"id":raw["id"],"text":raw["text"],"date":raw["date"],"label":raw["label"].strip().lower(),"split":split[raw["id"]]})
with (ROOT/"data/lexicon.json").open(encoding="utf-8") as f:lex=json.load(f)
tr=np.array([i for i,r in enumerate(rows) if r["split"]=="train"]);va=np.array([i for i,r in enumerate(rows) if r["split"]=="validation"])
features=[{k:r[k] for k in ("id","text","date")} for r in rows]
_,builder=feature_matrix(features,lex,tr)
model=CatBoostClassifier(task_type="CPU",thread_count=2,verbose=False);model.load_model(str(OUT/"catboost_gpu_pilot.cbm"))
adapter=PredictionAdapter(model,{k:v for k,v in builder.items() if k not in {"char_matrix","info"}},("false","true","unsure"),"catboost")
artifact_dir=OUT/"models"/"catboost_gpu_pilot";artifact_dir.mkdir(parents=True,exist_ok=True)
adapter_path=artifact_dir/"adapter.joblib";joblib.dump(adapter,adapter_path,compress=3)
valrows=[{k:rows[int(i)][k] for k in ("id","text","date")} for i in va]
with threadpool_limits(limits=2):adapter.predict_proba(valrows[:min(64,len(valrows))])
t=time.perf_counter()
with threadpool_limits(limits=2):probs=adapter.predict_proba(valrows)
elapsed=time.perf_counter()-t
result={"status":"COMPLETED","training":"GPU CatBoost model loaded for CPU inference","split":"validation; outer test skipped","rows":len(valrows),
        "cpu_two_thread_adapter_inference_seconds":elapsed,"cpu_two_thread_adapter_rows_per_second":len(valrows)/elapsed,
        "model_size_bytes":(OUT/"catboost_gpu_pilot.cbm").stat().st_size+adapter_path.stat().st_size,
        "native_model_size_bytes":(OUT/"catboost_gpu_pilot.cbm").stat().st_size,"adapter_size_bytes":adapter_path.stat().st_size,
        "probability_shape":list(probs.shape)}
(OUT/"catboost_gpu_pilot_cpu_inference.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
