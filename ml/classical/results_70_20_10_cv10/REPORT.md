# Classical model comparison — one 70/20/10 + grouped 10-fold run

## Protocol

- One fixed-seed benchmark run: 33 configurations and 330 grouped fold fits. CV used only the 70% training partition. The 20% validation partition selected among CV-winning family configurations; the 10% test partition was scored only for the selected model.
- Inference features: claim text, date, and lexicon-derived indicators. Gold `form` values were excluded from features; forms were used only for duplicate grouping and leakage audit.
- Candidates: TF-IDF + Logistic Regression, calibrated Linear SVM, CatBoost, and LightGBM; original, moderate, and balanced weighting variants.
- Elapsed: 441.6 seconds; selected fit on train+validation: 1.43 seconds; serialization: 0.07 seconds; peak process RSS: 571.3 MiB.

## Best configuration per family

| Family/configuration | CV macro-F1 | CV bal. acc. | Val. accuracy | Val. bal. acc. | Val. macro-F1 | FALSE P/R/F1 (n) | UNSURE P/R/F1 (n) | Size |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| logistic_regression / `logistic_regression:1.0::moderate` | 0.352 | 0.366 | 0.718 | 0.358 | 0.344 | 0.143 / 0.109 / 0.124 (n=55) | 0.048 / 0.125 / 0.069 (n=8) | 65.6 KiB |
| linear_svc / `linear_svc:1.0::none` | 0.303 | 0.333 | 0.834 | 0.333 | 0.303 | 0.000 / 0.000 / 0.000 (n=55) | 0.000 / 0.000 / 0.000 (n=8) | 144.2 KiB |
| catboost / `catboost:5:3:balanced` | 0.361 | 0.423 | 0.467 | 0.332 | 0.287 | 0.144 / 0.382 / 0.209 (n=55) | 0.023 / 0.125 / 0.038 (n=8) | 106.6 KiB |
| lightgbm / `lightgbm:15:1:balanced` | 0.367 | 0.370 | 0.718 | 0.368 | 0.384 | 0.133 / 0.145 / 0.139 (n=55) | 0.333 / 0.125 / 0.182 (n=8) | 282.5 KiB |

## Selected model and test metrics

**Selected: lightgbm** (`balanced`, leaves=15, lambda=1). CV selected the configuration within each family; validation selected the family. The test partition was not used for selection.

| Metric | Test result |
|---|---:|
| Accuracy | 0.747 |
| Balanced accuracy | 0.449 |
| Macro-F1 | 0.473 |
| ECE (10 bins) | 0.086 |
| Multiclass Brier | 0.361 |
| Full-adapter CPU throughput | 3112 rows/s |
| Estimated 20,000-row inference | 6.43 sec |
| Serialized size | 665.0 KiB |

| Test label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| false | 0.219 | 0.250 | 0.233 | 28 |
| true | 0.859 | 0.848 | 0.854 | 158 |
| unsure | 0.500 | 0.250 | 0.333 | 4 |

Confusion matrix (actual rows, predicted columns; order FALSE, TRUE, UNSURE):

```text
7 | 20 | 1
24 | 134 | 0
1 | 2 | 1
```

## Interpretation and caveats

- LightGBM led per-family CV macro-F1 (0.367) and validation macro-F1 (0.384). CatBoost had higher CV balanced accuracy (0.423) and validation FALSE recall (0.382), but lower macro-F1.
- Selected test accuracy (74.7%) is below the always-TRUE baseline (83.2%), while macro-F1 (0.473) and balanced accuracy (0.449) exceed that baseline (macro-F1 0.303; balanced accuracy 0.333). The model trades majority-class accuracy for minority-class coverage.
- Test UNSURE support is only 4; validation UNSURE support is 8. Treat these estimates as highly uncertain.
- Duplicate/near-duplicate claims and identical fact signatures are grouped. Broader subject/attribute history overlaps remain and are counted in `ml/shared/splitting_audit.json`, limiting temporal generalization claims.
- Logistic Regression and Linear SVM emitted convergence warnings in multiple folds; those comparisons may be under-optimized.
- Throughput includes adapter feature transformation plus CPU inference under a two-thread limit. The 20,000-row wall time is linearly projected from repeated 190-row batches, not directly timed on 20,000 rows.

Per-configuration CV OOF metrics and fold dispersion: `benchmark_results_70_20_10_cv10.csv`. Live progress/ETA: `benchmark_progress_70_20_10_cv10.json`.
