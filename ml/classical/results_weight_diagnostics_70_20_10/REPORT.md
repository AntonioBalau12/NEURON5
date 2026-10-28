# Targeted class weighting diagnostics

## Protocol and audit

- Used the existing seed-42 `70/20/10` split and the existing grouped 10-fold manifest: 1,328 train rows, 379 validation rows, and 190 outer-test rows.
- Only train and validation records were materialized from `practice.csv`; outer-test labels and forms were skipped. No outer-test metrics were produced.
- CV used out-of-fold probabilities: each training row was predicted by a model that excluded its assigned fold. The saved grouped manifests join duplicates, near duplicates, and fact-signature groups; broad subject/attribute histories still cross 165 outer partitions and 335 CV folds, as recorded in `ml/shared/splitting_audit.json`.
- Features were word and character TF-IDF plus claim date, lexicon entity/attribute mentions, numeric/currency/month counts, and text cues. The `form` field was excluded from the feature builder and adapter. Validation forms were joined only after predictions for error characterization.
- Existing CV `moderate` means square-root inverse-frequency weights normalized to mean sample weight 1. On the 1,328-row training partition, effective per-row weights (TRUE/FALSE/UNSURE) were **0.762 / 1.820 / 4.878**. `balanced` uses full inverse-frequency weights: **0.400 / 2.282 / 16.395**. CV fold ranges are in `class_weights.json`.

## Run and artifacts

The run completed on CPU with two-thread limits in **573.5 seconds** (9m 33.5s): 8.1s feature preparation, 170 grouped CV fits (14 LightGBM weight/base combinations and 3 CatBoost weight combinations), and 17 train-only validation refits. Startup ETA was explicitly uncalibrated at 374s; CatBoost fold times varied from 5.6s to 25.7s. The runner's original ETA median mixed the fast LightGBM folds with CatBoost; the source has since been updated to track per-family runtimes and avoid overwriting a completed run. Peak measured RSS among validation fits was 398.3 MiB.

- `oof_predictions.csv`: 22,576 records (17 configurations × 1,328 training rows), with each row's fold and three probabilities.
- `validation_predictions.csv`: 6,443 records (17 configurations × 379 validation rows).
- `weight_results.csv`: full metric, timing, throughput, size, and memory table for all configurations.
- `threshold_analysis.csv` and `threshold_summary.json`: 49 validation-only class-score policies.
- `validation_errors.csv`, `error_categories.csv`, and `representative_incorrect_predictions.csv`: error breakdown and 20 reviewed incorrect examples.
- `models/`: serialized adapters and CatBoost native files. Selected LightGBM adapter is 677,267 bytes; CatBoost sizes include native and adapter artifacts.
- `FEATURE_ROADMAP.md`: P0-compatible fact-feature implementation recommendations.

## LightGBM weight ranking

Ranked by aggregate OOF Macro-F1, using `num_leaves=15`, `reg_lambda=1` (the `reg_lambda=5` runs produced identical metrics for each vector).

| TRUE/FALSE/UNSURE weights | CV accuracy | CV balanced acc. | CV Macro-F1 | FALSE P/R/F1 | UNSURE recall | Validation accuracy | Validation Macro-F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 / 3 / 3 | 79.74% | 35.01% | **0.3462** | .234 / .113 / .153 | 0.000 | 78.89% | .3113 |
| 1 / 3 / 1 | 79.59% | 34.24% | .3356 | .198 / .088 / .121 | 0.000 | 79.16% | .3202 |
| 1 / 2 / 1 | 82.91% | 33.72% | .3150 | .267 / .021 / .038 | 0.000 | 78.89% | .3113 |
| 1 / 2 / 2 | 82.76% | 33.52% | .3116 | .188 / .015 / .029 | 0.000 | 79.16% | .3121 |
| 1 / 1.5 / 2 | 83.21% | 33.56% | .3095 | .286 / .010 / .020 | 0.000 | 79.95% | .3056 |
| 1 / 1.5 / 1 | 83.21% | 33.41% | .3062 | .200 / .005 / .010 | 0.000 | 79.95% | .3056 |
| 1 / 1 / 1 | **83.36%** | 33.33% | .3032 | .000 / .000 / .000 | 0.000 | **80.74%** | .3718 |

For context, the all-TRUE majority baseline is 83.36% CV accuracy and 83.38% validation accuracy, with zero FALSE/UNSURE recall and Macro-F1 0.303. No weight vector improved CV accuracy. Higher FALSE weights increased FALSE recall, but the best 1/3/3 vector lost 3.61 percentage points of CV accuracy and still detected no UNSURE rows. The modest accuracy-constrained choice is **1/2/1**: it is 0.45 points below baseline CV accuracy and gains 0.0118 Macro-F1, but FALSE recall remains only 2.1% and UNSURE recall remains zero. This is not a robust accuracy improvement.

CatBoost (depth 5, L2=3, 300 iterations) was repeated with 1/1/1, 1/3/3, and 1/2/1. Its best CV Macro-F1 was 0.3254 (1/3/3), below LightGBM's 0.3462. CatBoost did not improve the validation minority-class results; its validation FALSE and UNSURE recalls were zero for the accuracy-constrained 1/2/1 configuration. Thus the diagnostics do not justify replacing LightGBM with CatBoost.

### Separate GPU training pilot

The machine has an NVIDIA GeForce RTX 5060 Laptop GPU with 8,151 MiB VRAM. The controlled weight sweep above used CPU CatBoost and CPU LightGBM. A separate one-fit GPU pilot then trained CatBoost with the same 1/2/1 vector, depth 5, L2=3, 300 iterations, and the same train/validation rows. It completed the full-train fit in **3.28s**, versus **27.82s** for the CPU CatBoost 1/2/1 validation refit (8.5× faster in this one-fit measurement). Its validation result was 80.74% accuracy, 33.28% balanced accuracy, and 0.3169 Macro-F1; FALSE P/R/F1 were .143/.036/.058 and UNSURE recall was zero. Brier/ECE were .3202/.0771. The serialized native model plus adapter was **493,219 bytes**, and end-to-end CPU adapter inference was **3,256 rows/s** on the 379-row validation batch.

This GPU pilot was not part of grouped CV and must not replace the CV ranking: it is one training run with validation scoring. It is promising on measured fit time, model size, validation accuracy, and CPU inference rate, but its validation advantage is small and UNSURE was still missed. The GPU CatBoost output and CPU adapter prediction file are saved as `catboost_gpu_pilot.json`, `catboost_gpu_pilot_cpu_inference.json`, `catboost_gpu_pilot.cbm`, and `models/catboost_gpu_pilot/adapter.joblib`.

For the selected 1/2/1 LightGBM, CV accuracy / balanced accuracy / Macro-F1 were **82.91% / 33.72% / 0.3150**; CV FALSE precision/recall/F1 were **.267/.021/.038** (support 194), and UNSURE metrics were all zero for support 27. Its CV confusion matrix (actual rows and predicted columns; FALSE, TRUE, UNSURE) was `[[4,190,0],[10,1097,0],[1,26,0]]`.

Validation accuracy / balanced accuracy / Macro-F1 were **78.89% / 32.54% / 0.3113**. FALSE P/R/F1 were **.095/.036/.053** (support 55); UNSURE P/R/F1 were **0/0/0** (support 8). Confusion matrix: `[[2,53,0],[19,297,0],[0,8,0]]`. Brier score / 10-bin ECE were **.3445 / .1303** on validation, versus **.2936 / .0658** on OOF predictions. The validation probability calibration is weak and worse than CV.

The selected adapter scored validation at **2,203 rows/s** under the two-thread CPU limit. Fit time was 1.55s, serialization 0.11s, size 677,267 bytes, and measured validation-fit peak RSS 245 MiB. These are small validation-batch measurements, not a production load test.

## Validation-only decision policy analysis

Policies divide the FALSE and UNSURE class probabilities by the corresponding multiplier before choosing the maximum score. Multipliers below 1 raise a class's relative decision priority. The validation argmax was 78.89% accuracy, Macro-F1 .3113, FALSE recall 3.6%, and UNSURE recall 0%.

- Best validation accuracy used FALSE=1.0, UNSURE=0.2: **79.16% accuracy** (+0.26 points), Macro-F1 .3858, FALSE recall unchanged at 3.6%, and UNSURE precision/recall 1.00/.125 (one of eight UNSURE rows recovered).
- Best Macro-F1 subject to at most a two-point accuracy loss used FALSE=0.5, UNSURE=0.2: **78.63% accuracy** (-0.26 points), balanced accuracy .4000, Macro-F1 **.4315**, FALSE P/R/F1 .243/.164/.196, and UNSURE P/R/F1 1.00/.125/.222.
- That constrained policy produced 37 FALSE predictions: 9 correct FALSE predictions and 28 false alarms. It improves minority detection on this validation sample but does not establish a general accuracy gain.

The thresholds were selected and evaluated on the same 379 validation labels, including only 8 UNSURE examples. Treat these figures as policy diagnostics, not an unbiased final estimate. Keep the outer test untouched for the eventual single evaluation after policy selection.

## Error review

The selected model made 80 validation errors. At standard argmax it predicted FALSE 21 times: **2 correct FALSE predictions and 19 false alarms**. Among the 80 errors, 53 were originally FALSE, 19 TRUE, and 8 UNSURE. Sixty-eight involved numeric claims, 6 had a negation cue, 12 were multi-fact claims, and 47 had a quantity value kind. The most common error entities were Hooly Search (10), Hooly (9), and Hooly Gemini (7); the most common attribute was price (4). The most common claim date was 2026-10-26 (4 errors), tied with 2026-06-04 (4).

The 20 exported examples were individually reviewed. They include high-confidence FALSE-to-TRUE errors on numeric claims (for example p-181 and p-191), an UNSURE-to-TRUE error with probability TRUE .979 (p-404), and TRUE-to-FALSE errors on multi-fact or product/version claims (p-55 and p-24). Several wrong FALSE claims are dated measurements or quantities (p-146, p-343, p-367). This pattern is consistent with a text/date classifier lacking evidence comparison: lexical similarity cannot establish whether a reported number or named person is correct at the claim date. Gold forms were used to describe entities/attributes/value kinds after prediction only.

## P0 audit and next implementation step

The P0 `foundation.py` types provide `TypedValue`, `AtomicFact`, `EvidenceRecord`, `TemporalObservation`, and `CandidateFact`. `parse_evidence_form` validates supplied typed facts; it is not a claim-text semantic parser. `observations` marks true-row facts confirmed, but false-row facts have unknown atomic status. `evidence_audit` handles the existing typed evidence and as-of comparison logic. The P0 `runner.py` accepts text/date/label inputs and externally supplied candidates; it has no text parser or ML inference interface. Runtime input has no gold `form`.

Recommended next step: run grouped 10-fold CV for the GPU CatBoost 1/2/1 candidate (and the CV macro-F1 leader 1/3/3), keeping CPU adapter inference measurements and the same folds. That will establish whether the GPU pilot's small validation advantage repeats. Then implement one versioned text-to-candidate-fact parser using the P0 typed structures and lexicon, followed by a training-only evidence index consumed through the existing audit. Add, in order, parser coverage; subject/attribute exact match; typed kind and unit compatibility; compatible normalized numeric difference; as-of temporal consistency; confirmed support and explicit-contradiction counts. Missing/incompatible evidence must remain unknown, and false-row forms must never create negative evidence. Re-run grouped CV with identical fold IDs, then select the model and threshold policy before opening the outer test. See `FEATURE_ROADMAP.md` for details.

## Reproduction

From repository root, use a fresh output directory to preserve this completed run:

```powershell
$env:NEURON5_WEIGHT_OUT = "ml/classical/results_weight_diagnostics_rerun"
$env:UV_CACHE_DIR = (Resolve-Path "ml/classical/.uv-cache").Path
uv run --no-project --offline --python C:\Python312\python.exe `
  --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 `
  --with catboost==1.2.8 --with lightgbm==4.6.0 --with psutil==7.0.0 `
  --with joblib==1.5.1 python ml/classical/weight_diagnostics.py
```

The source records status, elapsed time, family-specific ETA, and projected finish in `progress.json`. This run's measured completion time was 573.5s; no durations in this report are estimates except the explicitly marked startup ETA.

The separate GPU pilot and its CPU-adapter timing can be reproduced with:

```powershell
uv run --no-project --offline --python C:\Python312\python.exe `
  --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 `
  --with catboost==1.2.8 --with lightgbm==4.6.0 --with psutil==7.0.0 `
  --with joblib==1.5.1 python ml/classical/catboost_gpu_pilot.py
uv run --no-project --offline --python C:\Python312\python.exe `
  --with numpy==2.2.6 --with scipy==1.15.3 --with scikit-learn==1.6.1 `
  --with catboost==1.2.8 --with lightgbm==4.6.0 --with psutil==7.0.0 `
  --with joblib==1.5.1 python ml/classical/measure_gpu_pilot_cpu_adapter.py
```
