# Final comparison (frozen extractor outputs)

Created 2026-10-28T19:10:19+00:00. Command: `experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_final.json --title Final comparison (frozen extractor outputs) --out experiments/evaluation/results/final`

Evaluation rows: **135** (120 held-out, 15 dev control). Form facts: **183**. Evaluator-suggested extra facts: **4** (unverified). Primary gold for the component metrics: `form`.
Bootstrap: 2000 resamples of rows, seed 20261028; cells read `value [95% interval] (numerator/denominator)`.

> **Small-sample caveat.** The set is small and purposive, not a random sample of the dataset. Intervals only capture row sampling noise, not label noise, the incompleteness of the form, or the stratification. Differences between methods inside each other's intervals should not be reported as differences. Absolute numbers do not generalise to the whole dataset.

## 1. Atomic fact precision / recall

`form` = facts of the dataset form (incomplete): precision against it is a *lower bound* of true precision and recall a *lower bound* of recall of what the sentence states. `suggested` = form + evaluator suggestions (unverified).

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| precision vs form | 83.7% [71-96] (41/49) | 97.4% [94-100] (114/117) | 94.3% [90-98] (115/122) | 98.2% [95-100] (107/109) | 93.8% [90-98] (122/130) | 93.8% [90-98] (122/130) |
| recall vs form | 22.4% [17-28] (41/183) | 62.3% [54-70] (114/183) | 62.8% [55-70] (115/183) | 58.5% [51-65] (107/183) | 66.7% [58-74] (122/183) | 66.7% [58-74] (122/183) |
| F1 vs form | 35.3% [28-43] (82/232) | 76.0% [69-82] (228/300) | 75.4% [69-81] (230/305) | 73.3% [67-79] (214/292) | 78.0% [72-83] (244/313) | 78.0% [72-83] (244/313) |
| precision vs suggested | 83.7% [71-96] (41/49) | 99.1% [97-100] (116/117) | 95.9% [92-99] (117/122) | 100.0% [100-100] (109/109) | 95.4% [91-99] (124/130) | 95.4% [91-99] (124/130) |
| recall vs suggested | 21.9% [16-28] (41/187) | 62.0% [54-70] (116/187) | 62.6% [55-70] (117/187) | 58.3% [51-65] (109/187) | 66.3% [58-74] (124/187) | 66.3% [58-74] (124/187) |
| F1 vs suggested | 34.7% [27-42] (82/236) | 76.3% [70-82] (232/304) | 75.7% [69-81] (234/309) | 73.6% [67-79] (218/296) | 78.2% [72-83] (248/317) | 78.2% [72-83] (248/317) |
| precision approx. upper bound (all extras not known wrong are right) | 83.7% [71-96] (41/49) | 99.1% [97-100] (116/117) | 99.2% [97-100] (121/122) | 100.0% [100-100] (109/109) | 98.5% [96-100] (128/130) | 98.5% [96-100] (128/130) |

## 2. Facts beyond the form and incorrect extractions

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| mapped facts on eval rows (distinct) | 49 | 117 | 122 | 109 | 130 | 130 |
| duplicates dropped | 0 | 0 | 0 | 0 | 0 | 0 |
| unmapped/abstained records | 0 | 43 | 0 | 0 | 0 | 0 |
| matching a form fact | 41 | 114 | 115 | 107 | 122 | 122 |
| **beyond the form (unverified candidates)** | 8 | 3 | 7 | 2 | 8 | 8 |
| &nbsp;&nbsp;matching an evaluator suggestion | 0 | 2 | 2 | 2 | 2 | 2 |
| &nbsp;&nbsp;not matching any suggestion | 8 | 1 | 5 | 0 | 6 | 6 |
| &nbsp;&nbsp;reviewed (judgements file) | 8 | 0 | 0 | 0 | 0 | 0 |
| &nbsp;&nbsp;judged correct | 0 | 0 | 0 | 0 | 0 | 0 |
| &nbsp;&nbsp;judged incorrect | 8 | 0 | 0 | 0 | 0 | 0 |
| &nbsp;&nbsp;judged unclear | 0 | 0 | 0 | 0 | 0 | 0 |
| &nbsp;&nbsp;not reviewed and not suggested | 0 | 1 | 5 | 0 | 6 | 6 |
| different value on a slot the form fills (likely wrong, automatic) | 3 | 1 | 1 | 0 | 2 | 2 |
| **known or likely incorrect** | 8 | 1 | 1 | 0 | 2 | 2 |

`known or likely incorrect` = judged incorrect + conflicting with a form slot (unless judged correct). Extras that are neither suggested nor reviewed are *unknown*: they may be right (the form is incomplete) or wrong. Review them with `judgement_template_unreviewed_candidates.csv` and pass the filled file with `--judgements`.

## 3. Component accuracy (against the primary gold)

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| exact canonical triple (= recall vs primary) | 22.4% [17-28] (41/183) | 62.3% [54-70] (114/183) | 62.8% [55-70] (115/183) | 58.5% [51-65] (107/183) | 66.7% [58-74] (122/183) | 66.7% [58-74] (122/183) |
| rows where all gold facts are found | 19.3% [13-26] (26/135) | 54.8% [47-63] (74/135) | 57.0% [49-65] (77/135) | 51.1% [43-59] (69/135) | 60.7% [53-68] (82/135) | 60.7% [53-68] (82/135) |
| rows where the fact set equals the gold set | 19.3% [13-26] (26/135) | 54.1% [46-62] (73/135) | 55.6% [47-63] (75/135) | 50.4% [42-59] (68/135) | 58.5% [50-66] (79/135) | 58.5% [50-66] (79/135) |
| entity recognition | 37.2% [27-47] (68/183) | 65.0% [56-73] (119/183) | 66.1% [57-74] (121/183) | 63.4% [55-71] (116/183) | 67.8% [59-76] (124/183) | 67.8% [59-76] (124/183) |
| &nbsp;&nbsp;subject written in the sentence | 52.3% [40-63] (68/130) | 88.5% [82-94] (115/130) | 90.0% [84-95] (117/130) | 86.2% [79-92] (112/130) | 92.3% [87-97] (120/130) | 92.3% [87-97] (120/130) |
| &nbsp;&nbsp;subject implicit (context only) | 0.0% [0-0] (0/53) | 7.5% [2-15] (4/53) | 7.5% [2-15] (4/53) | 7.5% [2-15] (4/53) | 7.5% [2-15] (4/53) | 7.5% [2-15] (4/53) |
| attribute mapping, given entity correct | 64.7% [55-77] (44/68) | 95.8% [93-99] (114/119) | 95.0% [90-99] (115/121) | 92.2% [87-97] (107/116) | 98.4% [96-100] (122/124) | 98.4% [96-100] (122/124) |
| value, given entity and attribute correct | 93.2% [85-100] (41/44) | 100.0% [100-100] (114/114) | 100.0% [100-100] (115/115) | 100.0% [100-100] (107/107) | 100.0% [100-100] (122/122) | 100.0% [100-100] (122/122) |
| gold slot filled with any value | 24.0% [18-30] (44/183) | 62.3% [54-70] (114/183) | 62.8% [55-70] (115/183) | 58.5% [51-65] (107/183) | 66.7% [58-74] (122/183) | 66.7% [58-74] (122/183) |

## 4. Negation and temporal extraction

Negation gold: boolean-false form facts must be extracted with `negated=true` (EXCHANGE_FORMAT). Temporal gold: cue words found by a regex plus evaluator override (`temporal_cues` in `evaluator_reference.json`); **no sentence of the set states an explicit observation date**, so only cue capture and non-fabrication can be measured. Validity intervals are not evaluated.

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| negation recall (false facts found with negated=true) | 28.6% [7-53] (4/14) | 35.7% [11-62] (5/14) | 42.9% [17-69] (6/14) | 28.6% [7-54] (4/14) | 50.0% [23-77] (7/14) | 50.0% [23-77] (7/14) |
| negation specificity (matched non-negated facts with negated=false) | 97.3% [91-100] (36/37) | 100.0% [100-100] (109/109) | 100.0% [100-100] (109/109) | 100.0% [100-100] (103/103) | 100.0% [100-100] (115/115) | 100.0% [100-100] (115/115) |
| negated flag correct on matched facts | 97.6% [92-100] (40/41) | 100.0% [100-100] (114/114) | 100.0% [100-100] (115/115) | 100.0% [100-100] (107/107) | 100.0% [100-100] (122/122) | 100.0% [100-100] (122/122) |
| exact fact + flag in rows with negation words | 26.3% [7-50] (5/19) | 36.8% [16-62] (7/19) | 42.1% [20-67] (8/19) | 31.6% [12-56] (6/19) | 47.4% [25-73] (9/19) | 47.4% [25-73] (9/19) |
| temporal cue captured in temporal_qualifier (cue rows) | 0.0% [0-0] (0/28) | 64.3% [46-82] (18/28) | 60.7% [42-78] (17/28) | 57.1% [38-75] (16/28) | 64.3% [45-81] (18/28) | 64.3% [45-81] (18/28) |
| &nbsp;&nbsp;given the method extracted a fact there | 0.0% [0-0] (0/10) | 80.0% [61-95] (16/20) | 81.0% [61-96] (17/21) | 84.2% [65-100] (16/19) | 81.8% [63-96] (18/22) | 81.8% [63-96] (18/22) |
| no qualifier on rows without a listed cue (with a fact) | 100.0% [100-100] (32/32) | 96.8% [92-100] (61/63) | 100.0% [100-100] (66/66) | 98.4% [95-100] (60/61) | 97.0% [92-100] (65/67) | 97.0% [92-100] (65/67) |
| dates set in observation/validity fields that the text supports | n/a | n/a | 100.0% (1/1) | 100.0% (1/1) | 100.0% (1/1) | 100.0% (1/1) |
| observation/validity dates set (count) | 0 | 0 | 1 | 1 | 1 | 1 |
| &nbsp;&nbsp;of which equal to the page date (count) | 0 | 0 | 0 | 0 | 0 | 0 |

## 5. By value kind (against the primary gold)

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| boolean: recall | 31.8% [12-52] (7/22) | 45.5% [25-65] (10/22) | 50.0% [29-70] (11/22) | 40.9% [21-62] (9/22) | 54.5% [33-75] (12/22) | 54.5% [33-75] (12/22) |
| boolean: precision | 87.5% [56-100] (7/8) | 100.0% [100-100] (10/10) | 100.0% [100-100] (11/11) | 100.0% [100-100] (9/9) | 100.0% [100-100] (12/12) | 100.0% [100-100] (12/12) |
| boolean: value given entity+attr ok | 87.5% [56-100] (7/8) | 100.0% [100-100] (10/10) | 100.0% [100-100] (11/11) | 100.0% [100-100] (9/9) | 100.0% [100-100] (12/12) | 100.0% [100-100] (12/12) |
| date: recall | 15.4% [0-38] (2/13) | 69.2% [43-93] (9/13) | 38.5% [12-69] (5/13) | 38.5% [12-69] (5/13) | 69.2% [43-93] (9/13) | 69.2% [43-93] (9/13) |
| date: precision | 100.0% [100-100] (2/2) | 100.0% [100-100] (9/9) | 71.4% [33-100] (5/7) | 100.0% [100-100] (5/5) | 81.8% [60-100] (9/11) | 81.8% [60-100] (9/11) |
| date: value given entity+attr ok | 100.0% [100-100] (2/2) | 100.0% [100-100] (9/9) | 100.0% [100-100] (5/5) | 100.0% [100-100] (5/5) | 100.0% [100-100] (9/9) | 100.0% [100-100] (9/9) |
| duration: recall | 6.2% [0-22] (1/16) | 87.5% [67-100] (14/16) | 87.5% [67-100] (14/16) | 87.5% [67-100] (14/16) | 87.5% [67-100] (14/16) | 87.5% [67-100] (14/16) |
| duration: precision | 100.0% (1/1) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) |
| duration: value given entity+attr ok | 100.0% (1/1) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) | 100.0% [100-100] (14/14) |
| money: recall | 0.0% [0-0] (0/19) | 78.9% [53-100] (15/19) | 68.4% [45-93] (13/19) | 68.4% [45-93] (13/19) | 78.9% [53-100] (15/19) | 78.9% [53-100] (15/19) |
| money: precision | n/a | 100.0% [100-100] (15/15) | 92.9% [79-100] (13/14) | 100.0% [100-100] (13/13) | 93.8% [85-100] (15/16) | 93.8% [85-100] (15/16) |
| money: value given entity+attr ok | n/a | 100.0% [100-100] (15/15) | 100.0% [100-100] (13/13) | 100.0% [100-100] (13/13) | 100.0% [100-100] (15/15) | 100.0% [100-100] (15/15) |
| name: recall | 0.0% [0-0] (0/19) | 36.8% [14-59] (7/19) | 57.9% [33-81] (11/19) | 36.8% [14-59] (7/19) | 57.9% [33-81] (11/19) | 57.9% [33-81] (11/19) |
| name: precision | n/a | 87.5% [56-100] (7/8) | 84.6% [67-100] (11/13) | 87.5% [56-100] (7/8) | 84.6% [67-100] (11/13) | 84.6% [67-100] (11/13) |
| name: value given entity+attr ok | n/a | 100.0% [100-100] (7/7) | 100.0% [100-100] (11/11) | 100.0% [100-100] (7/7) | 100.0% [100-100] (11/11) | 100.0% [100-100] (11/11) |
| percent: recall | 26.7% [7-53] (4/15) | 40.0% [12-69] (6/15) | 40.0% [12-69] (6/15) | 40.0% [12-69] (6/15) | 40.0% [12-69] (6/15) | 40.0% [12-69] (6/15) |
| percent: precision | 100.0% [100-100] (4/4) | 100.0% [100-100] (6/6) | 85.7% [50-100] (6/7) | 100.0% [100-100] (6/6) | 85.7% [50-100] (6/7) | 85.7% [50-100] (6/7) |
| percent: value given entity+attr ok | 100.0% [100-100] (4/4) | 100.0% [100-100] (6/6) | 100.0% [100-100] (6/6) | 100.0% [100-100] (6/6) | 100.0% [100-100] (6/6) | 100.0% [100-100] (6/6) |
| quantity: recall | 41.3% [29-54] (26/63) | 61.9% [49-74] (39/63) | 63.5% [51-75] (40/63) | 61.9% [49-74] (39/63) | 63.5% [51-75] (40/63) | 63.5% [51-75] (40/63) |
| quantity: precision | 78.8% [63-96] (26/33) | 97.5% [92-100] (39/40) | 100.0% [100-100] (40/40) | 100.0% [100-100] (39/39) | 97.6% [93-100] (40/41) | 97.6% [93-100] (40/41) |
| quantity: value given entity+attr ok | 92.9% [83-100] (26/28) | 100.0% [100-100] (39/39) | 100.0% [100-100] (40/40) | 100.0% [100-100] (39/39) | 100.0% [100-100] (40/40) | 100.0% [100-100] (40/40) |
| version: recall | 6.2% [0-21] (1/16) | 87.5% [69-100] (14/16) | 93.8% [80-100] (15/16) | 87.5% [69-100] (14/16) | 93.8% [80-100] (15/16) | 93.8% [80-100] (15/16) |
| version: precision | 100.0% (1/1) | 93.3% [78-100] (14/15) | 93.8% [80-100] (15/16) | 93.3% [78-100] (14/15) | 93.8% [80-100] (15/16) | 93.8% [80-100] (15/16) |
| version: value given entity+attr ok | 100.0% (1/1) | 100.0% [100-100] (14/14) | 100.0% [100-100] (15/15) | 100.0% [100-100] (14/14) | 100.0% [100-100] (15/15) | 100.0% [100-100] (15/15) |

## 6. By stratum (rows may be in several strata; recall/precision against form)

Cells: recall / precision.

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| implicit_attribute (n=48) | 11% [5-17] (9/79) / 69% [48-100] (9/13) | 68% [56-78] (54/79) / 98% [95-100] (54/55) | 66% [54-77] (52/79) / 93% [87-98] (52/56) | 61% [49-71] (48/79) / 100% [100-100] (48/48) | 73% [61-84] (58/79) / 92% [86-98] (58/63) | 73% [61-84] (58/79) / 92% [86-98] (58/63) |
| implicit_subject (n=46) | 0% [0-0] (0/56) / n/a | 12% [5-21] (7/56) / 100% [100-100] (7/7) | 12% [5-21] (7/56) / 88% [57-100] (7/8) | 12% [5-21] (7/56) / 100% [100-100] (7/7) | 12% [5-21] (7/56) / 88% [57-100] (7/8) | 12% [5-21] (7/56) / 88% [57-100] (7/8) |
| kind_boolean (n=22) | 26% [11-43] (7/27) / 88% [57-100] (7/8) | 41% [23-62] (11/27) / 100% [100-100] (11/11) | 48% [26-71] (13/27) / 93% [85-100] (13/14) | 37% [19-57] (10/27) / 100% [100-100] (10/10) | 52% [31-74] (14/27) / 93% [86-100] (14/15) | 52% [31-74] (14/27) / 93% [86-100] (14/15) |
| kind_date (n=13) | 15% [0-28] (3/20) / 75% [23-100] (3/4) | 65% [41-84] (13/20) / 100% [100-100] (13/13) | 55% [25-78] (11/20) / 85% [56-100] (11/13) | 45% [22-64] (9/20) / 100% [100-100] (9/9) | 75% [47-95] (15/20) / 88% [69-100] (15/17) | 75% [47-95] (15/20) / 88% [69-100] (15/17) |
| kind_duration (n=13) | 17% [0-35] (4/23) / 100% [100-100] (4/4) | 91% [78-100] (21/23) / 100% [100-100] (21/21) | 91% [78-100] (21/23) / 100% [100-100] (21/21) | 91% [78-100] (21/23) / 100% [100-100] (21/21) | 91% [78-100] (21/23) / 100% [100-100] (21/21) | 91% [78-100] (21/23) / 100% [100-100] (21/21) |
| kind_money (n=16) | 14% [4-22] (5/35) / 50% [33-100] (5/10) | 80% [64-92] (28/35) / 97% [92-100] (28/29) | 74% [58-90] (26/35) / 96% [91-100] (26/27) | 71% [57-86] (25/35) / 100% [100-100] (25/25) | 83% [66-95] (29/35) / 94% [86-100] (29/31) | 83% [66-95] (29/35) / 94% [86-100] (29/31) |
| kind_name (n=17) | 13% [4-21] (4/30) / 100% [100-100] (4/4) | 53% [30-70] (16/30) / 100% [100-100] (16/16) | 67% [40-85] (20/30) / 95% [87-100] (20/21) | 53% [30-70] (16/30) / 100% [100-100] (16/16) | 67% [40-85] (20/30) / 95% [87-100] (20/21) | 67% [40-85] (20/30) / 95% [87-100] (20/21) |
| kind_percent (n=14) | 29% [16-47] (7/24) / 70% [50-100] (7/10) | 54% [19-74] (13/24) / 93% [89-100] (13/14) | 46% [19-63] (11/24) / 85% [67-100] (11/13) | 46% [19-63] (11/24) / 100% [100-100] (11/11) | 54% [19-74] (13/24) / 81% [67-100] (13/16) | 54% [19-74] (13/24) / 81% [67-100] (13/16) |
| kind_quantity (n=56) | 32% [24-41] (28/88) / 82% [68-100] (28/34) | 65% [52-76] (57/88) / 97% [92-100] (57/59) | 65% [52-76] (57/88) / 93% [87-98] (57/61) | 62% [51-74] (55/88) / 98% [94-100] (55/56) | 67% [54-78] (59/88) / 92% [86-98] (59/64) | 67% [54-78] (59/88) / 92% [86-98] (59/64) |
| kind_version (n=16) | 9% [0-21] (2/23) / 100% [100-100] (2/2) | 87% [70-100] (20/23) / 95% [83-100] (20/21) | 87% [73-100] (20/23) / 95% [83-100] (20/21) | 83% [65-96] (19/23) / 95% [82-100] (19/20) | 91% [78-100] (21/23) / 95% [84-100] (21/22) | 91% [78-100] (21/23) / 95% [84-100] (21/22) |
| label_false (n=28) | 29% [15-43] (10/35) / 91% [71-100] (10/11) | 49% [28-67] (17/35) / 100% [100-100] (17/17) | 54% [34-72] (19/35) / 100% [100-100] (19/19) | 49% [28-67] (17/35) / 100% [100-100] (17/17) | 54% [34-72] (19/35) / 100% [100-100] (19/19) | 54% [34-72] (19/35) / 100% [100-100] (19/19) |
| label_true (n=99) | 21% [14-28] (29/139) / 81% [66-97] (29/36) | 68% [59-76] (94/139) / 97% [94-100] (94/97) | 67% [58-75] (93/139) / 93% [88-98] (93/100) | 63% [54-70] (87/139) / 98% [94-100] (87/89) | 72% [63-80] (100/139) / 93% [88-98] (100/108) | 72% [63-80] (100/139) / 93% [88-98] (100/108) |
| label_unsure (n=8) | 22% [0-56] (2/9) / 100% [100-100] (2/2) | 33% [0-75] (3/9) / 100% [100-100] (3/3) | 33% [0-75] (3/9) / 100% [100-100] (3/3) | 33% [0-75] (3/9) / 100% [100-100] (3/3) | 33% [0-75] (3/9) / 100% [100-100] (3/3) | 33% [0-75] (3/9) / 100% [100-100] (3/3) |
| likely_incomplete_form (n=22) | 8% [0-21] (2/24) / 100% [100-100] (2/2) | 62% [42-83] (15/24) / 88% [72-100] (15/17) | 54% [32-75] (13/24) / 76% [54-94] (13/17) | 54% [32-75] (13/24) / 87% [69-100] (13/15) | 62% [42-83] (15/24) / 79% [61-95] (15/19) | 62% [42-83] (15/24) / 79% [61-95] (15/19) |
| multi_fact (n=36) | 18% [11-25] (15/84) / 71% [54-100] (15/21) | 71% [59-83] (60/84) / 98% [96-100] (60/61) | 70% [58-82] (59/84) / 94% [88-98] (59/63) | 67% [55-78] (56/84) / 100% [100-100] (56/56) | 75% [62-86] (63/84) / 93% [87-98] (63/68) | 75% [62-86] (63/84) / 93% [87-98] (63/68) |
| negation (n=17) | 32% [14-56] (6/19) / 86% [55-100] (6/7) | 37% [16-61] (7/19) / 100% [100-100] (7/7) | 42% [21-67] (8/19) / 100% [100-100] (8/8) | 32% [11-56] (6/19) / 100% [100-100] (6/6) | 47% [25-74] (9/19) / 100% [100-100] (9/9) | 47% [25-74] (9/19) / 100% [100-100] (9/9) |
| numeric_confusable (n=61) | 26% [18-34] (25/97) / 86% [71-100] (25/29) | 68% [56-79] (66/97) / 97% [93-100] (66/68) | 67% [55-78] (65/97) / 94% [89-99] (65/69) | 65% [53-76] (63/97) / 98% [95-100] (63/64) | 70% [58-80] (68/97) / 93% [87-99] (68/73) | 70% [58-80] (68/97) / 93% [87-99] (68/73) |
| paraphrase (n=102) | 22% [16-28] (32/147) / 82% [68-97] (32/39) | 65% [56-74] (96/147) / 97% [93-100] (96/99) | 66% [57-74] (97/147) / 94% [90-98] (97/103) | 61% [53-69] (90/147) / 98% [94-100] (90/92) | 70% [61-79] (103/147) / 94% [89-98] (103/110) | 70% [61-79] (103/147) / 94% [89-98] (103/110) |
| temporal (n=44) | 23% [12-34] (14/60) / 88% [68-100] (14/16) | 75% [62-86] (45/60) / 100% [100-100] (45/45) | 72% [57-83] (43/60) / 96% [88-100] (43/45) | 67% [53-78] (40/60) / 100% [100-100] (40/40) | 80% [66-91] (48/60) / 96% [90-100] (48/50) | 80% [66-91] (48/60) / 96% [90-100] (48/50) |

## 7. Held-out versus dev control rows

Methods were tuned on dev rows, so dev rows are a *control*: a method that is much better on the 15 dev rows than on the 120 held-out rows is overfitted.

| metric | baseline | openie | slot_filling | combined_intersection | combined_union | combined_union_resolved |
|---|---|---|---|---|---|---|
| dev: recall_form | 19.0% [4-38] (4/21) | 71.4% [50-88] (15/21) | 85.7% [68-100] (18/21) | 71.4% [50-88] (15/21) | 85.7% [68-100] (18/21) | 85.7% [68-100] (18/21) |
| dev: precision_form | 80.0% [33-100] (4/5) | 100.0% [100-100] (15/15) | 100.0% [100-100] (18/18) | 100.0% [100-100] (15/15) | 100.0% [100-100] (18/18) | 100.0% [100-100] (18/18) |
| heldout: recall_form | 22.8% [17-29] (37/162) | 61.1% [52-69] (99/162) | 59.9% [51-68] (97/162) | 56.8% [48-65] (92/162) | 64.2% [55-73] (104/162) | 64.2% [55-73] (104/162) |
| heldout: precision_form | 84.1% [71-97] (37/44) | 97.1% [94-100] (99/102) | 93.3% [88-98] (97/104) | 97.9% [95-100] (92/94) | 92.9% [88-97] (104/112) | 92.9% [88-97] (104/112) |

## 8. Paired differences (same resampled rows)

| comparison | metric | difference (95% interval) |
|---|---|---|
| openie minus baseline | precision_form | +13.8 pts [2, 26] |
| openie minus baseline | recall_form | +39.9 pts [32, 48] |
| openie minus baseline | f1_form | +40.7 pts [33, 49] |
| openie minus baseline | precision_suggested | +15.5 pts [4, 27] |
| openie minus baseline | recall_suggested | +40.1 pts [33, 48] |
| openie minus baseline | f1_suggested | +41.6 pts [34, 49] |
| slot_filling minus baseline | precision_form | +10.6 pts [-2, 23] |
| slot_filling minus baseline | recall_form | +40.4 pts [33, 48] |
| slot_filling minus baseline | f1_form | +40.1 pts [33, 47] |
| slot_filling minus baseline | precision_suggested | +12.2 pts [0, 25] |
| slot_filling minus baseline | recall_suggested | +40.6 pts [34, 48] |
| slot_filling minus baseline | f1_suggested | +41.0 pts [34, 48] |
| combined_intersection minus baseline | precision_form | +14.5 pts [2, 28] |
| combined_intersection minus baseline | recall_form | +36.1 pts [29, 43] |
| combined_intersection minus baseline | f1_form | +37.9 pts [31, 45] |
| combined_intersection minus baseline | precision_suggested | +16.3 pts [4, 29] |
| combined_intersection minus baseline | recall_suggested | +36.4 pts [29, 43] |
| combined_intersection minus baseline | f1_suggested | +38.9 pts [32, 46] |
| combined_union minus baseline | precision_form | +10.2 pts [-2, 22] |
| combined_union minus baseline | recall_form | +44.3 pts [37, 52] |
| combined_union minus baseline | f1_form | +42.6 pts [35, 50] |
| combined_union minus baseline | precision_suggested | +11.7 pts [0, 23] |
| combined_union minus baseline | recall_suggested | +44.4 pts [37, 52] |
| combined_union minus baseline | f1_suggested | +43.5 pts [37, 51] |
| combined_union_resolved minus baseline | precision_form | +10.2 pts [-2, 22] |
| combined_union_resolved minus baseline | recall_form | +44.3 pts [37, 52] |
| combined_union_resolved minus baseline | f1_form | +42.6 pts [35, 50] |
| combined_union_resolved minus baseline | precision_suggested | +11.7 pts [0, 23] |
| combined_union_resolved minus baseline | recall_suggested | +44.4 pts [37, 52] |
| combined_union_resolved minus baseline | f1_suggested | +43.5 pts [37, 51] |

## 9. Resources

| method | CPU s | wall s | peak working set MB | exit code |
|---|---|---|---|---|
| baseline | 2.97 | 3.15 | 24.1 | 0 |
| openie | 2.16 | 2.28 | 25.9 | 0 |
| slot_filling | 2.2 | 2.31 | 22.5 | 0 |
| combined_intersection | not measured | not measured | not measured | not measured |
| combined_union | not measured | not measured | not measured | not measured |
| combined_union_resolved | not measured | not measured | not measured | not measured |

## 10. Files and coverage

| method | file | valid facts | invalid dropped | rows with a fact (all) | eval rows with a fact | sha1 |
|---|---|---|---|---|---|---|
| baseline | .\experiments\evaluation\output\baseline_facts.jsonl | 658 | 0 | 547/1897 | 42/135 | 9db1ee7521 |
| openie | .\experiments\openie\output\facts.jsonl | 2184 | 0 | 1734/1897 | 119/135 | 6c7bd87df5 |
| slot_filling | .\experiments\slot_filling\output\facts.jsonl | 1595 | 0 | 1222/1897 | 87/135 | a60e086b14 |
| combined_intersection | .\experiments\evaluation\output\combined_intersection_facts.jsonl | 1424 | 0 | 1132/1897 | 80/135 | 71499ae483 |
| combined_union | .\experiments\evaluation\output\combined_union_facts.jsonl | 1663 | 0 | 1239/1897 | 89/135 | 6cb4394237 |
| combined_union_resolved | .\experiments\evaluation\output\combined_union_resolved_facts.jsonl | 1658 | 0 | 1239/1897 | 89/135 | 9b9c0967d0 |
