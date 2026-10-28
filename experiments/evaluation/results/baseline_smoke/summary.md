# Baseline smoke test (pipeline proof; baseline only)

Created 2026-10-28T18:03:38+00:00. Command: `experiments/evaluation/evaluate.py --methods baseline --resources experiments/evaluation/_scratch/res_baseline.json --title Baseline smoke test (pipeline proof; baseline only) --out experiments/evaluation/results/baseline_smoke`

Evaluation rows: **135** (120 held-out, 15 dev control). Form facts: **183**. Evaluator-suggested extra facts: **4** (unverified). Primary gold for the component metrics: `form`.
Bootstrap: 2000 resamples of rows, seed 20261028; cells read `value [95% interval] (numerator/denominator)`.

> **Small-sample caveat.** The set is small and purposive, not a random sample of the dataset. Intervals only capture row sampling noise, not label noise, the incompleteness of the form, or the stratification. Differences between methods inside each other's intervals should not be reported as differences. Absolute numbers do not generalise to the whole dataset.

## 1. Atomic fact precision / recall

`form` = facts of the dataset form (incomplete): precision against it is a *lower bound* of true precision and recall a *lower bound* of recall of what the sentence states. `suggested` = form + evaluator suggestions (unverified).

| metric | baseline |
|---|---|
| precision vs form | 83.7% [71-96] (41/49) |
| recall vs form | 22.4% [17-28] (41/183) |
| F1 vs form | 35.3% [28-43] (82/232) |
| precision vs suggested | 83.7% [71-96] (41/49) |
| recall vs suggested | 21.9% [16-28] (41/187) |
| F1 vs suggested | 34.7% [27-42] (82/236) |
| precision approx. upper bound (all extras not known wrong are right) | 83.7% [71-96] (41/49) |

## 2. Facts beyond the form and incorrect extractions

| metric | baseline |
|---|---|
| mapped facts on eval rows (distinct) | 49 |
| duplicates dropped | 0 |
| unmapped/abstained records | 0 |
| matching a form fact | 41 |
| **beyond the form (unverified candidates)** | 8 |
| &nbsp;&nbsp;matching an evaluator suggestion | 0 |
| &nbsp;&nbsp;not matching any suggestion | 8 |
| &nbsp;&nbsp;reviewed (judgements file) | 8 |
| &nbsp;&nbsp;judged correct | 0 |
| &nbsp;&nbsp;judged incorrect | 8 |
| &nbsp;&nbsp;judged unclear | 0 |
| &nbsp;&nbsp;not reviewed and not suggested | 0 |
| different value on a slot the form fills (likely wrong, automatic) | 3 |
| **known or likely incorrect** | 8 |

`known or likely incorrect` = judged incorrect + conflicting with a form slot (unless judged correct). Extras that are neither suggested nor reviewed are *unknown*: they may be right (the form is incomplete) or wrong. Review them with `judgement_template_unreviewed_candidates.csv` and pass the filled file with `--judgements`.

## 3. Component accuracy (against the primary gold)

| metric | baseline |
|---|---|
| exact canonical triple (= recall vs primary) | 22.4% [17-28] (41/183) |
| rows where all gold facts are found | 19.3% [13-26] (26/135) |
| rows where the fact set equals the gold set | 19.3% [13-26] (26/135) |
| entity recognition | 37.2% [27-47] (68/183) |
| &nbsp;&nbsp;subject written in the sentence | 52.3% [40-63] (68/130) |
| &nbsp;&nbsp;subject implicit (context only) | 0.0% [0-0] (0/53) |
| attribute mapping, given entity correct | 64.7% [55-77] (44/68) |
| value, given entity and attribute correct | 93.2% [85-100] (41/44) |
| gold slot filled with any value | 24.0% [18-30] (44/183) |

## 4. Negation and temporal extraction

Negation gold: boolean-false form facts must be extracted with `negated=true` (EXCHANGE_FORMAT). Temporal gold: cue words found by a regex plus evaluator override (`temporal_cues` in `evaluator_reference.json`); **no sentence of the set states an explicit observation date**, so only cue capture and non-fabrication can be measured. Validity intervals are not evaluated.

| metric | baseline |
|---|---|
| negation recall (false facts found with negated=true) | 28.6% [7-53] (4/14) |
| negation specificity (matched non-negated facts with negated=false) | 97.3% [91-100] (36/37) |
| negated flag correct on matched facts | 97.6% [92-100] (40/41) |
| exact fact + flag in rows with negation words | 26.3% [7-50] (5/19) |
| temporal cue captured in temporal_qualifier (cue rows) | 0.0% [0-0] (0/28) |
| &nbsp;&nbsp;given the method extracted a fact there | 0.0% [0-0] (0/10) |
| no qualifier on rows without a listed cue (with a fact) | 100.0% [100-100] (32/32) |
| dates set in observation/validity fields that the text supports | n/a |
| observation/validity dates set (count) | 0 |
| &nbsp;&nbsp;of which equal to the page date (count) | 0 |

## 5. By value kind (against the primary gold)

| metric | baseline |
|---|---|
| boolean: recall | 31.8% [12-52] (7/22) |
| boolean: precision | 87.5% [56-100] (7/8) |
| boolean: value given entity+attr ok | 87.5% [56-100] (7/8) |
| date: recall | 15.4% [0-38] (2/13) |
| date: precision | 100.0% [100-100] (2/2) |
| date: value given entity+attr ok | 100.0% [100-100] (2/2) |
| duration: recall | 6.2% [0-22] (1/16) |
| duration: precision | 100.0% (1/1) |
| duration: value given entity+attr ok | 100.0% (1/1) |
| money: recall | 0.0% [0-0] (0/19) |
| money: precision | n/a |
| money: value given entity+attr ok | n/a |
| name: recall | 0.0% [0-0] (0/19) |
| name: precision | n/a |
| name: value given entity+attr ok | n/a |
| percent: recall | 26.7% [7-53] (4/15) |
| percent: precision | 100.0% [100-100] (4/4) |
| percent: value given entity+attr ok | 100.0% [100-100] (4/4) |
| quantity: recall | 41.3% [29-54] (26/63) |
| quantity: precision | 78.8% [63-96] (26/33) |
| quantity: value given entity+attr ok | 92.9% [83-100] (26/28) |
| version: recall | 6.2% [0-21] (1/16) |
| version: precision | 100.0% (1/1) |
| version: value given entity+attr ok | 100.0% (1/1) |

## 6. By stratum (rows may be in several strata; recall/precision against form)

Cells: recall / precision.

| metric | baseline |
|---|---|
| implicit_attribute (n=48) | 11% [5-17] (9/79) / 69% [48-100] (9/13) |
| implicit_subject (n=46) | 0% [0-0] (0/56) / n/a |
| kind_boolean (n=22) | 26% [11-43] (7/27) / 88% [57-100] (7/8) |
| kind_date (n=13) | 15% [0-28] (3/20) / 75% [23-100] (3/4) |
| kind_duration (n=13) | 17% [0-35] (4/23) / 100% [100-100] (4/4) |
| kind_money (n=16) | 14% [4-22] (5/35) / 50% [33-100] (5/10) |
| kind_name (n=17) | 13% [4-21] (4/30) / 100% [100-100] (4/4) |
| kind_percent (n=14) | 29% [16-47] (7/24) / 70% [50-100] (7/10) |
| kind_quantity (n=56) | 32% [24-41] (28/88) / 82% [68-100] (28/34) |
| kind_version (n=16) | 9% [0-21] (2/23) / 100% [100-100] (2/2) |
| label_false (n=28) | 29% [15-43] (10/35) / 91% [71-100] (10/11) |
| label_true (n=99) | 21% [14-28] (29/139) / 81% [66-97] (29/36) |
| label_unsure (n=8) | 22% [0-56] (2/9) / 100% [100-100] (2/2) |
| likely_incomplete_form (n=22) | 8% [0-21] (2/24) / 100% [100-100] (2/2) |
| multi_fact (n=36) | 18% [11-25] (15/84) / 71% [54-100] (15/21) |
| negation (n=17) | 32% [14-56] (6/19) / 86% [55-100] (6/7) |
| numeric_confusable (n=61) | 26% [18-34] (25/97) / 86% [71-100] (25/29) |
| paraphrase (n=102) | 22% [16-28] (32/147) / 82% [68-97] (32/39) |
| temporal (n=44) | 23% [12-34] (14/60) / 88% [68-100] (14/16) |

## 7. Held-out versus dev control rows

Methods were tuned on dev rows, so dev rows are a *control*: a method that is much better on the 15 dev rows than on the 120 held-out rows is overfitted.

| metric | baseline |
|---|---|
| dev: recall_form | 19.0% [4-38] (4/21) |
| dev: precision_form | 80.0% [33-100] (4/5) |
| heldout: recall_form | 22.8% [17-29] (37/162) |
| heldout: precision_form | 84.1% [71-97] (37/44) |

## 9. Resources

| method | CPU s | wall s | peak working set MB | exit code |
|---|---|---|---|---|
| baseline | 4.42 | 4.55 | 23.9 | 0 |

## 10. Files and coverage

| method | file | valid facts | invalid dropped | rows with a fact (all) | eval rows with a fact | sha1 |
|---|---|---|---|---|---|---|
| baseline | .\experiments\evaluation\output\baseline_facts.jsonl | 658 | 0 | 547/1897 | 42/135 | 9db1ee7521 |
