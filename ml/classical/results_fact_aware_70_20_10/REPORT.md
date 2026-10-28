# Classical ML + parser + temporal graph ablation

## Protocol

Used the fixed seed-42 70/20/10 split (1,328 train, 379 validation, 190 test) and the existing grouped 10-fold manifest. Exact/near duplicates and identical form signatures remain grouped. The shared audit reports 165 broad subject/attribute histories crossing outer splits and 335 crossing folds; semantically related histories are not fully isolated.

Each OOF graph contains only the other permitted training folds. Validation/test feature graphs contain only the training partition. Feature calls receive target text/date/ID; no target form is passed. Test labels/forms are joined only after predictions for final metrics/error review. Test results do not select models, weights, or thresholds.

All candidates use LightGBM: leaves=15, 300 estimators, learning_rate=.05, min_child_samples=20, reg_lambda=1, 2 CPU threads, fixed TRUE/FALSE/UNSURE weights 1/3/3. A uses current text/date/lexicon metadata; B adds 6 parser features; C adds 21 parser/evidence/temporal features; D uses structured features only. OOF and serving features exclude each target's own evidence ID.

## Results

| Model | Phase | Accuracy | Balanced acc. | Macro-F1 | TRUE P/R/F1 (n) | FALSE P/R/F1 (n) | UNSURE P/R/F1 (n) | Brier | ECE |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A_text_baseline | cv_oof | 80.27% | 35.92% | 0.3580 | 0.845/0.939/0.890 (1107) | 0.273/0.139/0.184 (194) | 0.000/0.000/0.000 (27) | 0.3302 | 0.1047 |
| B_text_parser | cv_oof | 79.59% | 35.37% | 0.3513 | 0.842/0.932/0.885 (1107) | 0.245/0.129/0.169 (194) | 0.000/0.000/0.000 (27) | 0.3324 | 0.1014 |
| C_text_parser_graph | cv_oof | 79.74% | 35.15% | 0.3481 | 0.842/0.936/0.886 (1107) | 0.237/0.119/0.158 (194) | 0.000/0.000/0.000 (27) | 0.3309 | 0.1000 |
| D_graph_only | cv_oof | 79.29% | 32.42% | 0.3079 | 0.831/0.947/0.885 (1107) | 0.076/0.026/0.038 (194) | 0.000/0.000/0.000 (27) | 0.3638 | 0.1530 |
| A_text_baseline | validation | 78.89% | 32.54% | 0.3113 | 0.830/0.940/0.881 (316) | 0.095/0.036/0.053 (55) | 0.000/0.000/0.000 (8) | 0.3506 | 0.1026 |
| B_text_parser | validation | 78.89% | 32.54% | 0.3113 | 0.830/0.940/0.881 (316) | 0.095/0.036/0.053 (55) | 0.000/0.000/0.000 (8) | 0.3511 | 0.1170 |
| C_text_parser_graph | validation | 77.57% | 32.51% | 0.3150 | 0.829/0.921/0.873 (316) | 0.107/0.055/0.072 (55) | 0.000/0.000/0.000 (8) | 0.3493 | 0.1025 |
| D_graph_only | validation | 81.00% | 33.39% | 0.3179 | 0.836/0.965/0.896 (316) | 0.143/0.036/0.058 (55) | 0.000/0.000/0.000 (8) | 0.3555 | 0.1796 |
| A_text_baseline | test | 78.95% | 44.67% | 0.4969 | 0.847/0.911/0.878 (158) | 0.263/0.179/0.213 (28) | 1.000/0.250/0.400 (4) | 0.3359 | 0.0756 |
| B_text_parser | test | 79.47% | 37.73% | 0.3789 | 0.848/0.918/0.881 (158) | 0.316/0.214/0.255 (28) | 0.000/0.000/0.000 (4) | 0.3278 | 0.0916 |
| C_text_parser_graph | test | 78.95% | 44.67% | 0.4969 | 0.847/0.911/0.878 (158) | 0.263/0.179/0.213 (28) | 1.000/0.250/0.400 (4) | 0.3296 | 0.1142 |
| D_graph_only | test | 81.05% | 32.49% | 0.2984 | 0.828/0.975/0.895 (158) | 0.000/0.000/0.000 (28) | 0.000/0.000/0.000 (4) | 0.3818 | 0.1980 |

Confusion matrices use actual/predicted order `false, true, unsure`; class metrics, prediction distributions, Brier score, and ECE are in `ablation_metrics.csv`.
Validation: parser extracted at least one fact from 97/379 (25.59%); usable graph evidence was available for 12/379 (3.17%).
Test: parser extracted at least one fact from 43/190 (22.63%); usable graph evidence was available for 7/190 (3.68%).

## Findings

C vs A on grouped OOF: Macro-F1 0.3481 vs 0.3580, accuracy 79.74% vs 80.27%. On validation, Macro-F1 0.3150 vs 0.3113 and FALSE recall 0.055 vs 0.036, with accuracy 77.57% vs 78.89%. On untouched test, Macro-F1 0.4969 vs 0.4969, accuracy 78.95% vs 78.95%, FALSE recall 0.179 vs 0.179, UNSURE recall 0.250 vs 0.250. No consistent held-out improvement is established.
B did not improve validation metrics and trailed A on OOF Macro-F1. D's validation/test accuracy does not justify selection: its CV and test Macro-F1 and minority recall are poor. Keep A as the current choice.
Majority-TRUE accuracy is 83.36% on train, 83.38% on validation, and 83.16% on test. The 1:3:3 class weights intentionally trade accuracy for minority-class recall.

## Graph and temporal semantics

Graph modules were copied unchanged from `feat/p1-temporal-graph`; P0 `foundation.py` and `runner.py` were not modified. Only forms from valid TRUE rows become verified support. FALSE-row facts remain unverified candidates, and text extraction never verifies a candidate. The graph has no verified-refutation producer and does not infer transitions/validity intervals from observation dates. Numerical/date mismatch is recorded only as a feature; absent evidence never becomes FALSE.
The feature `best_evidence_similarity` is lowercase token-frequency cosine similarity against evidence text; typed comparability is separately stored as `best_value_compatibility`. Event-like attributes use a documented attribute-name heuristic to compare event values across observation dates. General semantic parsing, pronouns, clause scope, and broad temporal state reasoning remain unsupported.

## Holdan date paraphrase check

- `Holdan joined Hooly on January 12, 2026.` parsed `[{'subject': 'Holdan', 'attribute': 'joined', 'value_kind': 'date', 'value': '2026-01-12', 'unit': None, 'currency': None}]`; exact match=1, date difference=0.0. Evidence IDs: p-1, p-46.
- `Holdan joined Hooly on January 13, 2026.` parsed `[{'subject': 'Holdan', 'attribute': 'joined', 'value_kind': 'date', 'value': '2026-01-13', 'unit': None, 'currency': None}]`; exact match=0, date difference=1.0. Evidence IDs: p-1, p-46.
The p-1 TRUE training form was reference evidence only. The one-day mismatch is not assigned a FALSE label.

## Error review and runtime
Validation comparison has 379 rows: 292 correct in both, 2 A-wrong/C-correct, 7 A-correct/C-wrong, 78 wrong in both. The 30-row representative file includes at least 20 rows incorrect under A or C, plus examples correct in both; it records parsed facts, evidence IDs, feature values, label/predictions, post-prediction forms, and why the argmax changed. Parser failures, missing evidence, and multi-fact claims occurred; no temporal mismatches or same-time evidence conflicts occurred in validation, so the separate Holdan example covers the temporal mismatch behavior. Validation FALSE predictions: A 21 (2 correct, 19 false alarms); C 28 (3 correct, 25 false alarms).
Total benchmark elapsed 446.03s, two CPU threads. Peak sampled RSS 157.9 MiB. Fit, inference, serialization size, and per-fold timings are in `timings.csv`.
End-to-end feature preparation: text vectorizer transform 0.57s, reference graph build 1.42s, validation feature extraction 9.49s, test extraction 4.76s. Repeated model-only batch inference rates are:
- A_text_baseline: 33,850 validation rows/s; 29,423 test rows/s; adapter 677,522 bytes.
- B_text_parser: 36,005 validation rows/s; 31,761 test rows/s; adapter 678,676 bytes.
- C_text_parser_graph: 35,167 validation rows/s; 32,787 test rows/s; adapter 677,663 bytes.
- D_graph_only: 73,894 validation rows/s; 73,229 test rows/s; adapter 438,745 bytes.

## Recommendation

**Does adding the Temporal Evidence Graph improve honest held-out classification? No reproducible improvement was measured.** It produced a small validation Macro-F1 increase alongside an accuracy loss, and did not establish a gain on the outer test. Given low parser/evidence coverage, retain the baseline and improve parsing plus evidence retrieval first. The previous best Classical ML Macro-F1 reference was 0.3674; see this report’s own OOF figures and split notes before comparing.

Reproduce from repository root:

```powershell
$env:UV_CACHE_DIR = (Resolve-Path 'ml/classical/.uv-cache').Path
uv run --no-project --offline --python C:\Python312\python.exe --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 --with lightgbm==4.6.0 --with psutil==7.0.0 --with joblib==1.5.1 python ml/classical/fact_aware_experiment.py
```
