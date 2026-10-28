"""Measure feature building and saved-model CPU inference throughput."""
import csv, json, statistics, time, sys
from pathlib import Path
import joblib, numpy as np, psutil
from scipy.sparse import csr_matrix, hstack
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from benchmark import LABELS, load_rows, load_shared_splits, transform_features, make_feature_builder
from fact_aware_experiment import OUT, graph_from_references, extract_rows, make_x, SPLIT_NAMES
from fact_aware_features import FEATURE_NAMES
from foundation import Lexicon

def main():
    rows,rawlex=load_rows(); splits,_=load_shared_splits(rows)
    refs=[r for r in rows if splits[r['id']]=='train']; val=[r for r in rows if splits[r['id']]=='validation']; test=[r for r in rows if splits[r['id']]=='test']
    lex,issues=Lexicon.parse(rawlex)
    if lex is None:raise ValueError(issues)
    proc=psutil.Process()
    builder=make_feature_builder(refs,rawlex)
    for name in SPLIT_NAMES:
        bundle=joblib.load(OUT/'models'/f'{name}.joblib');bundle['text_builder']=builder
        joblib.dump(bundle,OUT/'models'/f'{name}.joblib',compress=3)
    t=time.perf_counter(); base_x,_=transform_features(rows,builder); text_transform_sec=time.perf_counter()-t
    t=time.perf_counter(); graph=graph_from_references(refs,lex); graph_build_sec=time.perf_counter()-t
    t=time.perf_counter(); _,valdetails=extract_rows(val,graph,lex); val_extract_sec=time.perf_counter()-t
    t=time.perf_counter(); _,testdetails=extract_rows(test,graph,lex); test_extract_sec=time.perf_counter()-t
    fit_ids={r['id']:i for i,r in enumerate(rows)}
    train_ix=np.array([fit_ids[r['id']] for r in refs]); val_ix=np.array([fit_ids[r['id']] for r in val]); test_ix=np.array([fit_ids[r['id']] for r in test])
    trainvals=np.asarray([[d['feature_values'][k] for k in FEATURE_NAMES] for d in graph_details(refs,graph,lex)],dtype=np.float32)
    valvals=np.asarray([[d['feature_values'][k] for k in FEATURE_NAMES] for d in valdetails],dtype=np.float32)
    testvals=np.asarray([[d['feature_values'][k] for k in FEATURE_NAMES] for d in testdetails],dtype=np.float32)
    train_parser=csr_matrix(trainvals[:,:6]); train_graph=csr_matrix(trainvals)
    val_parser=csr_matrix(valvals[:,:6]); val_graph=csr_matrix(valvals)
    test_parser=csr_matrix(testvals[:,:6]); test_graph=csr_matrix(testvals)
    matrix={}
    for name in SPLIT_NAMES:
        train_x=make_x(base_x[train_ix],train_parser,train_graph,name)
        val_x=make_x(base_x[val_ix],val_parser,val_graph,name)
        test_x=make_x(base_x[test_ix],test_parser,test_graph,name)
        model=joblib.load(OUT/'models'/f'{name}.joblib')['model']
        rates={}
        for split,x in (('validation',val_x),('test',test_x)):
            durations=[]; rss=[]
            with threadpool_limits(limits=2):
                for _ in range(25):
                    before=proc.memory_info().rss/1024**2; start=time.perf_counter(); model.predict_proba(x); durations.append(time.perf_counter()-start); rss.append(proc.memory_info().rss/1024**2)
            median=statistics.median(durations)
            rates[split]={'rows':x.shape[0],'median_batch_seconds_25_repeats':median,'rows_per_second':x.shape[0]/median,'peak_sampled_rss_mb':max(rss)}
        file=OUT/'models'/f'{name}.joblib'
        matrix[name]={'serialized_model_bytes':file.stat().st_size,**rates}
    measurements={'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'thread_limit':2,'repeats_per_batch':25,
      'text_matrix_transform_seconds':text_transform_sec,'training_reference_graph_build_seconds':graph_build_sec,
      'validation_parser_graph_feature_extraction_seconds':val_extract_sec,'test_parser_graph_feature_extraction_seconds':test_extract_sec,
      'validation_rows':len(val),'test_rows':len(test),'models':matrix,
      'interpretation':'Model inference timing excludes text and graph feature building; preceding extraction durations measure those stages separately.'}
    (OUT/'inference_measurements.json').write_text(json.dumps(measurements,indent=2)+'\n',encoding='utf-8')
    # Add measurement columns to the saved timing table; fit durations remain from the actual run.
    path=OUT/'timings.csv'; old=list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    fields=list(dict.fromkeys([k for r in old for k in r]+['validation_inference_seconds','test_inference_seconds','validation_rows_per_second','test_rows_per_second','serialized_model_bytes','serialization_seconds','feature_graph_build_seconds','validation_feature_extraction_seconds','test_feature_extraction_seconds','peak_rss_mb']))
    for row in old:
        if row.get('phase')=='validation_and_test_refit':
            m=matrix[row['model_configuration']]
            row.update({'validation_inference_seconds':m['validation']['median_batch_seconds_25_repeats'],'test_inference_seconds':m['test']['median_batch_seconds_25_repeats'],'validation_rows_per_second':m['validation']['rows_per_second'],'test_rows_per_second':m['test']['rows_per_second'],'serialized_model_bytes':m['serialized_model_bytes'],'serialization_seconds':'','feature_graph_build_seconds':graph_build_sec,'validation_feature_extraction_seconds':val_extract_sec,'test_feature_extraction_seconds':test_extract_sec,'peak_rss_mb':max(m['validation']['peak_sampled_rss_mb'],m['test']['peak_sampled_rss_mb'])})
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(old)
    print(json.dumps(measurements,indent=2))

def graph_details(rows,graph,lex):
    return extract_rows(rows,graph,lex)[1]

if __name__=='__main__':main()
