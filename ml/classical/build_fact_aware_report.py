"""Finalize compact ablation metrics, error coverage, and experiment report."""
import csv,json,re
from collections import Counter,defaultdict
from pathlib import Path

BASE=Path(__file__).resolve().parent; OUT=BASE/'results_fact_aware_70_20_10'
CONFIGS=('A_text_baseline','B_text_parser','C_text_parser_graph','D_graph_only')
def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(path,rows,fields=None):
    if not rows:return
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def js(x):return json.loads(x) if isinstance(x,str) else x
def pct(x):return f'{100*x:.2f}%'

raw=read(OUT/'ablation_metrics.csv'); metrics=[]
for r in raw:
    if 'classes' not in r:
        clean={k:v for k,v in r.items()}
        for k in ('accuracy','balanced_accuracy','macro_f1','multiclass_brier','ece_10bin','false_precision','false_recall','false_f1','true_precision','true_recall','true_f1','unsure_precision','unsure_recall','unsure_f1'):
            clean[k]=float(clean[k])
        for k in ('false_support','true_support','unsure_support'):
            clean[k]=int(clean[k])
        metrics.append(clean);continue
    classes=js(r['classes']); cm=js(r['confusion_matrix']); preds=js(r['predicted'])
    metrics.append({'model_configuration':r['model_configuration'],'phase':r['phase'],'accuracy':float(r['accuracy']),'balanced_accuracy':float(r['balanced_accuracy']),'macro_f1':float(r['macro_f1']),
      'false_precision':classes['false']['precision'],'false_recall':classes['false']['recall'],'false_f1':classes['false']['f1'],'false_support':classes['false']['support'],
      'true_precision':classes['true']['precision'],'true_recall':classes['true']['recall'],'true_f1':classes['true']['f1'],'true_support':classes['true']['support'],
      'unsure_precision':classes['unsure']['precision'],'unsure_recall':classes['unsure']['recall'],'unsure_f1':classes['unsure']['f1'],'unsure_support':classes['unsure']['support'],
      'per_class_metrics_json':json.dumps(classes,separators=(',',':')),'confusion_matrix_labels':'false,true,unsure','confusion_matrix_json':json.dumps(cm,separators=(',',':')),
      'predicted_distribution_json':json.dumps(dict(Counter(preds)),separators=(',',':')),'multiclass_brier':float(r['multiclass_brier']),'ece_10bin':float(r['ece_10bin'])})
write(OUT/'ablation_metrics.csv',metrics)
by={(m['model_configuration'],m['phase']):m for m in metrics}

errors=read(OUT/'validation_error_analysis.csv'); cats=defaultdict(Counter); bucket_counts=Counter(); false_counts=Counter(); specials={}
for e in errors:
    try: fs=[x for x in js(e.get('form_for_post_prediction_review') or '[]') if isinstance(x,dict)]
    except Exception: fs=[]
    try: fv=js(e.get('feature_values') or '{}')
    except Exception: fv={}
    gold=e['gold_label']; text=e['text']; rid=e['row_id']
    correct_a=(e['baseline_prediction']==gold);correct_c=(e['hybrid_prediction']==gold)
    bucket='baseline_and_hybrid_correct' if correct_a and correct_c else 'baseline_wrong_hybrid_correct' if (not correct_a and correct_c) else 'baseline_correct_hybrid_wrong' if (correct_a and not correct_c) else 'both_wrong'
    bucket_counts[bucket]+=1
    if e['baseline_prediction']==e['hybrid_prediction']: why='Argmax unchanged after structured features.'
    elif correct_c: why='Structured features shifted argmax to the gold class; usable graph evidence '+('was available.' if float(fv.get('evidence_available') or 0)>0 else 'was absent, so the shift used parser/other structured features.')
    else: why='Structured features shifted argmax away from the gold class; usable graph evidence '+('was available.' if float(fv.get('evidence_available') or 0)>0 else 'was absent.')
    e['why_prediction_changed']=why;e['review_bucket']=bucket
    entities={str(x.get('subject','unknown')) for x in fs} or {'unknown'}; attrs={str(x.get('attribute','unknown')) for x in fs} or {'unknown'}
    kinds={str((x.get('value') or {}).get('kind','unknown')) for x in fs} or {'unknown'}
    flags={'numeric':bool(re.search(r'(?<!\w)\d+(?:[.,]\d+)?',text)),'negation':bool(re.search(r'\b(?:not|never|no|without|neither|nor|isn\'t|wasn\'t|doesn\'t|didn\'t|cannot)\b',text,re.I)),'multi_fact':len(fs)>1 or float(fv.get('parsed_fact_count') or 0)>1}
    for group,values in [('original_class',[gold]),('entity',entities),('attribute',attrs),('value_kind',kinds),('date',[e['date']]),('text_type',[k for k,v in flags.items() if v])]:
        for val in values:cats[group][val]+=1
    if not float(fv.get('parsed_fact_count') or 0):specials.setdefault('parser_failure',e)
    if not float(fv.get('evidence_available') or 0):specials.setdefault('missing_graph_evidence',e)
    try:
        if float(fv.get('date_difference_days'))>0:specials.setdefault('temporal_mismatch',e)
    except (TypeError,ValueError):pass
    if float(fv.get('conflict_count') or 0)>0:specials.setdefault('conflicting_evidence',e)
    if flags['multi_fact']:specials.setdefault('multi_fact',e)
    if e['baseline_prediction']=='false':false_counts['A_false_predictions']+=1;false_counts['A_correct_false' if gold=='false' else 'A_false_alarm']+=1
    if e['hybrid_prediction']=='false':false_counts['C_false_predictions']+=1;false_counts['C_correct_false' if gold=='false' else 'C_false_alarm']+=1
write(OUT/'validation_error_analysis.csv',errors)
cat_rows=[{'category':g,'value':v,'validation_row_count':n} for g,c in cats.items() for v,n in c.most_common()]
write(OUT/'validation_error_categories.csv',cat_rows,['category','value','validation_row_count'])
original=read(OUT/'representative_error_review.csv'); chosen=[];seen=set()
for category,e in specials.items():
    if e['row_id'] not in seen:chosen.append({**e,'review_bucket':category});seen.add(e['row_id'])
wrong_count=sum(e['baseline_prediction']!=e['gold_label'] or e['hybrid_prediction']!=e['gold_label'] for e in chosen)
for e in errors:
    if e['row_id'] in seen or (e['baseline_prediction']==e['gold_label'] and e['hybrid_prediction']==e['gold_label']):continue
    chosen.append(e);seen.add(e['row_id']);wrong_count+=1
    if wrong_count>=20:break
for e in original:
    if e['row_id'] in seen:continue
    full=next((x for x in errors if x['row_id']==e['row_id']),e)
    chosen.append(full);seen.add(e['row_id'])
    if len(chosen)>=30:break
write(OUT/'representative_error_review.csv',chosen)

coverage=json.loads((OUT/'coverage_summary.json').read_text(encoding='utf-8'))
run=json.loads((OUT/'run_report.json').read_text(encoding='utf-8'))
line=['# Classical ML + parser + temporal graph ablation','','## Protocol','',
"Used the fixed seed-42 70/20/10 split (1,328 train, 379 validation, 190 test) and the existing grouped 10-fold manifest. Exact/near duplicates and identical form signatures remain grouped. The shared audit reports 165 broad subject/attribute histories crossing outer splits and 335 crossing folds; semantically related histories are not fully isolated.",'',
"Each OOF graph contains only the other permitted training folds. Validation/test feature graphs contain only the training partition. Feature calls receive target text/date/ID; no target form is passed. Test labels/forms are joined only after predictions for final metrics/error review. Test results do not select models, weights, or thresholds.",'',
"All candidates use LightGBM: leaves=15, 300 estimators, learning_rate=.05, min_child_samples=20, reg_lambda=1, 2 CPU threads, fixed TRUE/FALSE/UNSURE weights 1/3/3. A uses current text/date/lexicon metadata; B adds 6 parser features; C adds 21 parser/evidence/temporal features; D uses structured features only. OOF and serving features exclude each target's own evidence ID.",'','## Results','','| Model | Phase | Accuracy | Balanced acc. | Macro-F1 | TRUE P/R/F1 (n) | FALSE P/R/F1 (n) | UNSURE P/R/F1 (n) | Brier | ECE |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for phase in ('cv_oof','validation','test'):
    for name in CONFIGS:
        m=by[(name,phase)];line.append(f"| {name} | {phase} | {pct(m['accuracy'])} | {pct(m['balanced_accuracy'])} | {m['macro_f1']:.4f} | {m['true_precision']:.3f}/{m['true_recall']:.3f}/{m['true_f1']:.3f} ({m['true_support']}) | {m['false_precision']:.3f}/{m['false_recall']:.3f}/{m['false_f1']:.3f} ({m['false_support']}) | {m['unsure_precision']:.3f}/{m['unsure_recall']:.3f}/{m['unsure_f1']:.3f} ({m['unsure_support']}) | {m['multiclass_brier']:.4f} | {m['ece_10bin']:.4f} |")
line+=['','Confusion matrices use actual/predicted order `false, true, unsure`; class metrics, prediction distributions, Brier score, and ECE are in `ablation_metrics.csv`.']
for split in ('validation','test'):
    c=coverage[split];line.append(f"{split.title()}: parser extracted at least one fact from {c['parser_rows_with_fact']}/{c['rows']} ({pct(c['parser_row_coverage'])}); usable graph evidence was available for {c['rows_with_graph_evidence']}/{c['rows']} ({pct(c['graph_row_coverage'])}).")
A=by[('A_text_baseline','cv_oof')];C=by[('C_text_parser_graph','cv_oof')];Av=by[('A_text_baseline','validation')];Cv=by[('C_text_parser_graph','validation')];At=by[('A_text_baseline','test')];Ct=by[('C_text_parser_graph','test')]
line += ['', '## Findings','',f"C vs A on grouped OOF: Macro-F1 {C['macro_f1']:.4f} vs {A['macro_f1']:.4f}, accuracy {pct(C['accuracy'])} vs {pct(A['accuracy'])}. On validation, Macro-F1 {Cv['macro_f1']:.4f} vs {Av['macro_f1']:.4f} and FALSE recall {Cv['false_recall']:.3f} vs {Av['false_recall']:.3f}, with accuracy {pct(Cv['accuracy'])} vs {pct(Av['accuracy'])}. On untouched test, Macro-F1 {Ct['macro_f1']:.4f} vs {At['macro_f1']:.4f}, accuracy {pct(Ct['accuracy'])} vs {pct(At['accuracy'])}, FALSE recall {Ct['false_recall']:.3f} vs {At['false_recall']:.3f}, UNSURE recall {Ct['unsure_recall']:.3f} vs {At['unsure_recall']:.3f}. No consistent held-out improvement is established.",
"B did not improve validation metrics and trailed A on OOF Macro-F1. D's validation/test accuracy does not justify selection: its CV and test Macro-F1 and minority recall are poor. Keep A as the current choice.",
f"Majority-TRUE accuracy is {pct(run['label_counts']['train']['true']/run['dataset_counts']['train'])} on train, {pct(run['label_counts']['validation']['true']/run['dataset_counts']['validation'])} on validation, and {pct(run['label_counts']['test']['true']/run['dataset_counts']['test'])} on test. The 1:3:3 class weights intentionally trade accuracy for minority-class recall.",
'','## Graph and temporal semantics','',
"Graph modules were copied unchanged from `feat/p1-temporal-graph`; P0 `foundation.py` and `runner.py` were not modified. Only forms from valid TRUE rows become verified support. FALSE-row facts remain unverified candidates, and text extraction never verifies a candidate. The graph has no verified-refutation producer and does not infer transitions/validity intervals from observation dates. Numerical/date mismatch is recorded only as a feature; absent evidence never becomes FALSE.",
"The feature `best_evidence_similarity` is lowercase token-frequency cosine similarity against evidence text; typed comparability is separately stored as `best_value_compatibility`. Event-like attributes use a documented attribute-name heuristic to compare event values across observation dates. General semantic parsing, pronouns, clause scope, and broad temporal state reasoning remain unsupported.",
'','## Holdan date paraphrase check','']
temporal_path=OUT/'temporal_paraphrase_check.json'
if temporal_path.exists():
    t=json.loads(temporal_path.read_text(encoding='utf-8'))
    for x in t['results']:
        f=x['features'];line.append(f"- `{x['claim_text']}` parsed `{x['parsed_facts']}`; exact match={f['exact_value_match']:.0f}, date difference={f['date_difference_days']}. Evidence IDs: {', '.join(e['evidence_id'] for e in x['retrieved_evidence'])}.")
    line.append('The p-1 TRUE training form was reference evidence only. The one-day mismatch is not assigned a FALSE label.')
line += ['','## Error review and runtime',f"Validation comparison has {len(errors)} rows: {bucket_counts['baseline_and_hybrid_correct']} correct in both, {bucket_counts['baseline_wrong_hybrid_correct']} A-wrong/C-correct, {bucket_counts['baseline_correct_hybrid_wrong']} A-correct/C-wrong, {bucket_counts['both_wrong']} wrong in both. The 30-row representative file includes at least 20 rows incorrect under A or C, plus examples correct in both; it records parsed facts, evidence IDs, feature values, label/predictions, post-prediction forms, and why the argmax changed. Parser failures, missing evidence, and multi-fact claims occurred; no temporal mismatches or same-time evidence conflicts occurred in validation, so the separate Holdan example covers the temporal mismatch behavior. Validation FALSE predictions: A {false_counts['A_false_predictions']} ({false_counts['A_correct_false']} correct, {false_counts['A_false_alarm']} false alarms); C {false_counts['C_false_predictions']} ({false_counts['C_correct_false']} correct, {false_counts['C_false_alarm']} false alarms).",
f"Total benchmark elapsed {run['elapsed_seconds']:.2f}s, two CPU threads. Peak sampled RSS {max(float(r['peak_rss_mb']) for r in read(OUT/'timings.csv') if r.get('peak_rss_mb')):.1f} MiB. Fit, inference, serialization size, and per-fold timings are in `timings.csv`."]
inference=OUT/'inference_measurements.json'
if inference.exists():
    im=json.loads(inference.read_text(encoding='utf-8'))
    line.append(f"End-to-end feature preparation: text vectorizer transform {im['text_matrix_transform_seconds']:.2f}s, reference graph build {im['training_reference_graph_build_seconds']:.2f}s, validation feature extraction {im['validation_parser_graph_feature_extraction_seconds']:.2f}s, test extraction {im['test_parser_graph_feature_extraction_seconds']:.2f}s. Repeated model-only batch inference rates are:")
    for name,m in im['models'].items():line.append(f"- {name}: {m['validation']['rows_per_second']:,.0f} validation rows/s; {m['test']['rows_per_second']:,.0f} test rows/s; adapter {m['serialized_model_bytes']:,} bytes.")
line += ['', '## Recommendation','', '**Does adding the Temporal Evidence Graph improve honest held-out classification? No reproducible improvement was measured.** It produced a small validation Macro-F1 increase alongside an accuracy loss, and did not establish a gain on the outer test. Given low parser/evidence coverage, retain the baseline and improve parsing plus evidence retrieval first. The previous best Classical ML Macro-F1 reference was 0.3674; see this report’s own OOF figures and split notes before comparing.', '', 'Reproduce from repository root:', '', '```powershell', "$env:UV_CACHE_DIR = (Resolve-Path 'ml/classical/.uv-cache').Path", 'uv run --no-project --offline --python C:\\Python312\\python.exe --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 --with lightgbm==4.6.0 --with psutil==7.0.0 --with joblib==1.5.1 python ml/classical/fact_aware_experiment.py', '```']
(OUT/'REPORT.md').write_text('\n'.join(line)+'\n',encoding='utf-8')
print('Wrote compact metrics, category/error files, and REPORT.md')
