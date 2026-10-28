# Item 1: does extraction improve classification of hidden-label rows?

[M] measured by the scripts here, [U] unverified or a hypothesis. Nothing is human-verified. Two runs, both designed before they were run; no parameter was tuned on the test rows.

## Setup
- **Test rows:** the 270 held-out rows (222 true, 41 false, 7 unsure), labels hidden. No extractor saw their forms. "Always true" scores **82.2%**.
- **Rule (mine, transparent, the same for every method):** an extracted atom is *supported* if evidence states the same value within W=14 days, *contradicted* if evidence states a different comparable value for the same subject and attribute and nothing agrees. Any contradicted atom makes the row `false`, otherwise `true`. `unsure` is never predicted.
- **This is not the team's classifier.** The repo's `ReasoningEngine` cannot output "false" (no refutation records exist), so I could not reuse it. Whether the competition scores accuracy, macro-F1 or something with confidence is not stated in the files I read.
- **Oracle:** the gold form as the atoms, i.e. perfect extraction, same rule.

## Results [M]

Run 1: evidence = dev rows labelled true, with gold forms (`results/run1`).

| Method | Accuracy | vs always-true (paired 95%) | F1 on `false` | False rows caught (of 41) | True rows wrongly flagged (of 222) |
|---|---|---|---|---|---|
| Always true | 82.2% | n/a | 0.0% | 0 | 0 |
| Old parser | 82.6% | +0.4 [-1.9, +2.6] | 20.0% | 5 | 4 |
| OpenIE-style | 83.3% | +1.1 [-1.9, +3.7] | 32.1% | 9 | 6 |
| Slot filling | 84.1% | +1.9 [-0.4, +4.1] | 30.8% | 8 | 3 |
| Union | 83.0% | +0.7 [-2.2, +3.7] | 31.6% | 9 | 7 |
| Intersection | 84.4% | +2.2 [0.0, +4.4] | 31.4% | 8 | 2 |
| **Oracle (gold form)** | **86.3%** | **+4.1 [+0.7, +7.8]** | 51.6% | 16 | 5 |

- Finding false rows, extractors vs old parser (paired F1 difference): OpenIE +12.1 [+1.3, +25.0], slot filling +10.8 [+0.4, +22.8], union +11.6, intersection +11.4. The intervals just exclude zero.
- Absolute level is low: even perfect extraction catches 16 of 41 false rows.

Realistic density (evidence thinned to 10% of the dev true rows, 135 rows, 5 seeds): every method is 82.4 to 82.7%, **and the oracle is 82.5%**. With this little labelled evidence, nothing helps.

Run 2: unlabelled consensus (other rows vote, labels ignored; `results/consensus_run1`). Primary rule: a contradiction needs 2 other rows.
- All rows as the pool: parser +0.4, OpenIE 0.0, slot filling +0.4, union -0.4, intersection +0.7, **oracle +1.1** [-0.4, +3.0].
- Held-out rows only as the pool: every extractor +0.0; oracle +0.4.
- Sensitivity (a contradiction needs 1 row): oracle +1.5 [-2.2, +5.6], extractors -1.1 to +0.7. Not distinguishable from zero.

Window sensitivity (run 1, accuracy): W=3 to 30 days give 82 to 85%. W=100000 (no window) drops the extractors to 76 to 79%.

## Why the ceiling is low [M]
Of the 41 false held-out rows, the gold atoms contradict the evidence within 14 days for 16 rows, only beyond 14 days for 23 rows, and not at all for 2. The values change over time. A longer window catches more false rows but flags true rows whose value later changed (5 of 222 true rows are wrongly flagged even with perfect atoms, e.g. `p-258` "Series A not yet raised").

## What this means
1. **With this evidence-lookup mechanism, extraction quality is not the bottleneck.** Perfect extraction is worth at most about +4 points of accuracy over "always true" (+1.1 to +1.5 with unlabelled voting). The measured extractors get roughly +1 to +2, not significant.
2. **The one robust gain** is that extractors flag false rows about 11 to 12 F1 points better than the old parser.
3. **The limit is knowing which value holds on a given date.** That needs temporal reasoning over value changes, not more facts.
4. **Not tested** [U]: a learned text classifier (features from the sentence itself or from agreement of the extractors), the team's real classifier in `ml/`, other metrics, a larger test set.

## Limits
- 41 false rows and 7 unsure rows: wide intervals, and `unsure` is never predicted here.
- The pool "all" in run 2 is optimistic, since dev rows trained the extractors.
- No human has checked whether the rule's verdicts on true rows (e.g. the 5 flagged) are errors of the rule or of the labels.

## Reproduce
```
$env:PYTHONUTF8='1'
py experiments/classification_test/classify_test.py --out experiments/classification_test/results/<new>
py experiments/classification_test/classify_consensus.py --out experiments/classification_test/results/<new2>
```
