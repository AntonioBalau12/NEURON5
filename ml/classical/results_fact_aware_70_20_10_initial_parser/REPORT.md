# Classical ML + parser + temporal graph ablation

## Protocol

Used the fixed seed-42 70/20/10 manifest (`ml/shared/splits.csv`; 1,328 train, 379 validation, 190 outer test) and existing grouped CV folds (`ml/shared/cv10_folds.csv`). Exact/near duplicate and form-signature groups are held together; the shared audit reports 165 broad subject/attribute history links across outer partitions and 335 across folds. These related histories are not fully group-isolated, so CV estimates may be optimistic for new entities/histories.

For every fold, graph evidence was built only from the other permitted training folds. Validation and test features used training partition evidence only. Target feature calls receive text/date/ID only; target `form` is not supplied. Test forms and labels are joined only after test predictions for the final score and post-prediction diagnostics. No threshold or model selection used test results.

All four configurations use LightGBM (15 leaves, 300 estimators, learning rate .05, min child 20, L2=1, two CPU threads) with the same TRUE/FALSE/UNSURE row weights 1/3/3. A is text/date/lexicon metadata; B adds six deterministic parser features; C adds all 20 parser/evidence/temporal features; D uses those 20 structured features alone. OOF features for model-training rows exclude that row's own evidence ID.

## Results

| Config | Phase | Accuracy | Balanced acc. | Macro-F1 | FALSE P/R/F1 | UNSURE P/R/F1 | Brier | ECE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A_text_baseline | cv_oof | 80.27% | 35.92% | 0.3580 | 0.273/0.139/0.184 (n=194) | 0.000/0.000/0.000 (n=27) | 0.3302 | 0.1047 |
| B_text_parser | cv_oof | 79.59% | 35.37% | 0.3513 | 0.245/0.129/0.169 (n=194) | 0.000/0.000/0.000 (n=27) | 0.3324 | 0.1014 |
| C_text_parser_graph | cv_oof | 79.74% | 35.15% | 0.3481 | 0.237/0.119/0.158 (n=194) | 0.000/0.000/0.000 (n=27) | 0.3309 | 0.0982 |
| D_graph_only | cv_oof | 79.59% | 32.54% | 0.3090 | 0.083/0.026/0.039 (n=194) | 0.000/0.000/0.000 (n=27) | 0.3628 | 0.1581 |
| A_text_baseline | validation | 78.89% | 32.54% | 0.3113 | 0.095/0.036/0.053 (n=55) | 0.000/0.000/0.000 (n=8) | 0.3506 | 0.1026 |
| B_text_parser | validation | 78.89% | 32.54% | 0.3113 | 0.095/0.036/0.053 (n=55) | 0.000/0.000/0.000 (n=8) | 0.3511 | 0.1170 |
| C_text_parser_graph | validation | 77.57% | 32.51% | 0.3150 | 0.107/0.055/0.072 (n=55) | 0.000/0.000/0.000 (n=8) | 0.3493 | 0.1025 |
| D_graph_only | validation | 80.47% | 32.67% | 0.3073 | 0.071/0.018/0.029 (n=55) | 0.000/0.000/0.000 (n=8) | 0.3548 | 0.1834 |
| A_text_baseline | test | 78.95% | 44.67% | 0.4969 | 0.263/0.179/0.213 (n=28) | 1.000/0.250/0.400 (n=4) | 0.3359 | 0.0756 |
| B_text_parser | test | 79.47% | 37.73% | 0.3789 | 0.316/0.214/0.255 (n=28) | 0.000/0.000/0.000 (n=4) | 0.3278 | 0.0916 |
| C_text_parser_graph | test | 78.95% | 44.67% | 0.4969 | 0.263/0.179/0.213 (n=28) | 1.000/0.250/0.400 (n=4) | 0.3296 | 0.1142 |
| D_graph_only | test | 81.05% | 32.49% | 0.2993 | 0.000/0.000/0.000 (n=28) | 0.000/0.000/0.000 (n=4) | 0.3802 | 0.1886 |

Confusion matrices in all phases use actual/predicted label order `false, true, unsure`; exact matrices and prediction distributions are in `ablation_metrics.csv`.

Validation parser emitted ≥1 fact for 97/379 claims (25.59%); at least one usable graph evidence record was available for 12/379 (3.17%).
Test parser emitted ≥1 fact for 43/190 claims (22.63%); at least one usable graph evidence record was available for 7/190 (3.68%).

## Findings

The graph did not produce a reproducible improvement. On grouped OOF, C was below A by 0.98 macro-F1 points (0.3481 vs 0.3580), 0.78 accuracy points (79.74% vs 80.27%), and 0.78 balanced-accuracy points. On validation, C gained 0.0036 macro-F1 (0.3150 vs 0.3113) and +1.82 points of FALSE recall, but lost 1.32 points accuracy (77.57% vs 78.89%); UNSURE recall remained zero. On the untouched test set, C produced exactly the same confusion matrix and metrics as A: 78.95% accuracy, 0.4969 macro-F1, FALSE recall 17.86%, and UNSURE recall 25% (1/4). It therefore demonstrated no measured outer-test improvement.

B did not improve validation metrics and was below A on OOF macro-F1. D's higher test accuracy is not a selection result: validation macro-F1 was lower and FALSE/UNSURE recall were near zero. Keep A as the selected baseline; improve parser/graph coverage before considering integration.

The practice majority TRUE accuracy is 83.36% in train/CV and 83.38% in validation; 83.16% in test. The 1:3:3 weights intentionally trade accuracy for minority detection, and none of the ablations reaches the majority baseline on validation/test.

## Graph and temporal semantics

Inspected `core/graph` from `feat/p1-temporal-graph`. Only valid forms from true rows become `VERIFIED_SUPPORT`; false-row forms stay `UNVERIFIED_CANDIDATE`; parser extraction is never verified. The graph's current resolver returns exact matching support and same-time conflicts, but has no producer of `VERIFIED_REFUTATION`. Observation dates do not imply persistence or a change interval. The feature builder therefore records comparable typed/date differences and exact-date/explicit-interval compatibility without converting mismatch or absent evidence to FALSE. Event-like attributes are matched across observation dates using an attribute-name heuristic, with mismatch remaining a feature only.

Parser candidate coverage is low (about one quarter of validation/test rows), while usable graph evidence is about 3–4%. Evidence similarity, typed differences, and dates are missing where the parser could not emit an atom or no compatible history exists. The parser does not implement general paraphrase/coreference or arbitrary clause semantics; no NLI model was used.

## Error review and runtime

The validation review contains 379 rows, including 292 correct under both models, 2 baseline-wrong/hybrid-correct, 7 baseline-correct/hybrid-wrong, and 78 wrong under both. `representative_error_review.csv` includes at least 20 examples with text/date, gold label, parsed facts, evidence IDs, relevant features, predictions, and post-prediction form for review. `validation_error_categories.csv` summarizes entity, attribute, value kind, date, original class, numeric, negation, and multi-fact groups. A FALSE prediction is a correct FALSE when gold is false and otherwise a false alarm; validation counts: A 21 false predictions (2 correct, 19 false alarms); C 28 (3 correct, 25 false alarms).

Full run elapsed 458.05 seconds on this 2-thread CPU-limited execution. Fit/feature-independent CPU inference, training, serialization sizes, and sampled RSS are in `timings.csv`; current measurements include small batch prediction timings and should not be read as production-scale serving throughput. Sampled max RSS is below 160 MiB. Model files are about 1.0–1.3 MB, but they intentionally omit serialized graph evidence; runtime must rebuild the evidence graph from eligible training inputs.

The previous best reported Classical ML Macro-F1 reference was 0.3674; this experiment's A OOF macro-F1 is 0.3580. Different score references should be compared only with the same exact split/features/protocol.

## Recommendation

**Adding this implementation of the Temporal Evidence Graph did not improve honest held-out classification.** It slightly improved validation Macro-F1 while reducing validation accuracy, but the effect did not carry to the untouched test set and was supported by graph evidence on only a small fraction of claims. Keep the baseline, expand semantic parsing and ensure temporal/subject/attribute coverage first, then repeat grouped CV and validation before final selection.

Reproduce with `uv run --no-project --offline --python C:\Python312\python.exe --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 --with lightgbm==4.6.0 --with psutil==7.0.0 --with joblib==1.5.1 python ml/classical/fact_aware_experiment.py`.
