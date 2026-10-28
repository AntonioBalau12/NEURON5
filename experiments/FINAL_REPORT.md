# NEURON5 P3: fact reconstruction and claim generation. Final report

Written 2026-10-28 evening. Nothing is committed. Branch `feat/p3-fact-reconstruction-research` (worktree `NEURON5-p3`), based on `origin/feat/p1-temporal-graph` at `f75f514`. P0 and `core/graph` are unchanged.

**Labels used throughout:** **[M]** measured by code in this repo and re-runnable. **[R]** a review by a language model (me or a subagent), not a human. **[E]** estimate or extrapolation. **[U]** unverified.
**No human has verified any fact, extraction or claim in this project.**

## 0. Read this first

1. **The extractors beat the existing parser on recall by a wide margin, and precision did not suffer.** On the 135-row evaluation set, recall against `form` goes from 22.4% to 62 to 67%, and precision against `form` from 83.7% to 94 to 98%. [M]
2. **The premise that `form` is badly incomplete was not borne out.** The evaluator's reading found a stated-but-missing fact in about 4 of 135 rows. OpenIE and slot filling together produced 8 distinct beyond-form facts on the set, and I judge **1 correct, 1 uncertain, 6 incorrect** [R]. (The old parser's own 8 beyond-form facts were all judged incorrect by the evaluator model.) Reconstruction recovers almost no new true facts; its gain is reading the facts the form already has.
3. **Reconstruction adds 0 claims** to the claim factory under every rule tried. The safe generator makes **411** claims, 589 short of 1,000. [M]
4. **No improvement in classification can be claimed.** No retraining or classification test was run.
5. **Statistical power is low.** 135 rows, 183 form facts. Most differences between the extractors, and between combinations, lie inside each other's 95% intervals.

## 1. What was done, and how

| Item | Detail |
|---|---|
| Contract and split | Common fact format and validator (`shared/EXCHANGE_FORMAT.md`, `shared/fact_schema.py`). Fixed split: 1,627 dev rows, 270 held-out (`sha1(id) % 100 < 15`). Extractors saw only `id, text, date` at run time |
| Subagents | **The platform cannot select a model, so Gemini 3.8 Flash and Haiku were not used.** All four packages ran on the platform default model. Several launches reported "cancelled" while the agents kept running; I judged progress by files on disk |
| Isolation | By instruction only, not enforced. Static audit [M]: runtime modules read gold forms only from `dev_rows.csv`, contain no hard-coded row ids, and the learned tables name no held-out id. This does not prove absence of leakage |
| Frozen outputs | `shared/FROZEN_FACTS.json` records sha1 of all three fact files. Re-checked unchanged after scoring [M] |
| Ordering | The evaluation set was chosen before any extractor output existed (file-system times, `evaluation/eval_set/selection_provenance_addendum.json`). The evaluator re-ran selection once at 19:39 before any output; the first selection's hash is kept |
| Sequential run | One process at a time, 3 repeats, 2 threads, affinity pinned to two logical CPUs. The laptop was busy with browser and chat apps, so timings are noisy |

The two extractors are **not real OpenIE or neural slot filling.** Both are standard-library Python, rule plus count-table systems with cue tables learned from dev forms. "OpenIE" here is "relation words to attribute scoring". spaCy installed on Python 3.14 but was never run, and Stanford OpenIE was never tried (only Java 8). **Neither technique was evaluated; they were dropped on environment grounds.**

## 2. Mandatory ablation table

Evaluation set: 135 rows (120 held-out, 15 dev control), 183 form facts. Intervals are 95% row bootstraps. Source: `evaluation/results/final/summary.md`.

| Approach | Fact precision (vs form) | Fact recall (vs form) | Correct new facts (beyond form) | CPU time (1,897 rows) | Extra valid claims |
|---|---|---|---|---|---|
| Existing parser | 83.7% [71-96] (41/49) [M] | 22.4% [17-28] (41/183) [M] | 0 of 8 beyond-form, all judged incorrect [R] | 2.97 s [M] | baseline: 411 claims from practice forms, not from the parser |
| OpenIE-style | 97.4% [94-100] (114/117) [M] | 62.3% [54-70] (114/183) [M] | 3 beyond form: 1 correct, 1 uncertain, 1 incorrect [R] | 2.16 s [M] | +0 [M] |
| Slot filling | 94.3% [90-98] (115/122) [M] | 62.8% [55-70] (115/183) [M] | 7 beyond form: 1 correct, 1 uncertain, 5 incorrect [R] | 2.20 s [M] | +0 [M] |
| Union (OpenIE + slot filling) | 93.8% [90-98] (122/130) [M] | 66.7% [58-74] (122/183) [M] | 8 beyond form: 1 correct, 1 uncertain, 6 incorrect [R] | 5.75 s (2.16 + 2.20 + 1.39) [M, summed] | +0 [M] |
| Intersection (both agree) | 98.2% [95-100] (107/109) [M] | 58.5% [51-65] (107/183) [M] | 2 beyond form: 1 correct, 1 uncertain [R] | 5.75 s | +0 [M] |

Notes on the table:
- **Precision and recall against `form` are lower and upper limits of the truth.** The form is not exhaustive, so a correct extra counts against precision. Because beyond-form extras are only 2 to 8 facts, this bias is small here: the "all extras right" upper bound is 99.1% (OpenIE) and 99.2% (slot filling) [M].
- **Correct new facts** are the one thing no human has checked. My review is in `shared/coordinator_review_beyond_form.csv`. The one correct fact is `Hooly head_of_security = Ron LaFlame` (p-1568), found by both methods and also suggested by the evaluator.
- **CPU time** is process CPU seconds on the full 1,897-row input, median of 3, including interpreter start. The slot-filling run used the **current** code, which differs from the frozen output (see section 8).
- **Extra valid claims** is relative to `run_main` (411 claims).
- `union_resolved` gives identical numbers to `union` on this set.

## 3. Component results

All [M] on the 135 rows, form as gold.

| Metric | Parser | OpenIE | Slot filling | Union | Intersection |
|---|---|---|---|---|---|
| Entity recognition | 37.2% | 65.0% | 66.1% | 67.8% | 63.4% |
| Subject written in sentence (n=130) | 52.3% | 88.5% | 90.0% | 92.3% | 86.2% |
| Subject only in context (n=53) | 0.0% | 7.5% | 7.5% | 7.5% | 7.5% |
| Attribute, given entity | 64.7% | 95.8% | 95.0% | 98.4% | 92.2% |
| Value, given entity and attribute | 93.2% | 100% | 100% | 100% | 100% |
| Held-out only: recall / precision (n=120 rows) | 22.8 / 84.1 | 61.1 / 97.1 | 59.9 / 93.3 | 64.2 / 92.9 | 56.8 / 97.9 |

- **The ceiling is about 71% recall for any method that reads one sentence.** 53 of 183 form facts have a subject that is not written in the sentence. The best method gets 4 of those 53.
- Value reading is not the problem: once entity and attribute are right, the value is right in every case (the form's own `op` values aside).
- Held-out and dev-control rows agree in direction. The 15 dev rows score higher (OpenIE 71% recall, slot filling 86%), which is the expected sign of tuning on dev.

### Dates, numbers, negation (Q2 detail)

| Kind | Parser recall / precision | OpenIE | Slot filling | Union |
|---|---|---|---|---|
| Date | 15% / 100% (2/2) | 69% / 100% (9/9) | 38% / 71% (5/7) | 69% / 82% (9/11) |
| Money | 0% / n/a | 79% / 100% (15/15) | 68% / 93% (13/14) | 79% / 94% |
| Quantity | 41% / 79% | 62% / 97.5% | 63% / 100% | 63% / 98% |
| Percent | 27% / 100% | 40% / 100% | 40% / 86% | 40% / 86% |
| Duration | 6% / 100% | 88% / 100% | 88% / 100% | 88% / 100% |
| Version | 6% / 100% | 88% / 93% | 94% / 94% | 94% / 94% |
| Name | 0% / n/a | 37% / 88% | 58% / 85% | 58% / 85% |
| Boolean | 32% / 88% | 45% / 100% | 50% / 100% | 55% / 100% |

- **Negation is weak for every method.** Boolean-false facts found with `negated=true`: parser 4/14, OpenIE 5/14, slot filling 6/14, union 7/14. When a method does flag one, polarity is right in every matched case (100%).
- Numbers and dates, when read, are exact. The failures are in subject and attribute assignment, not in parsing the value.
- Temporal words are captured as raw qualifiers: OpenIE 18/28, slot filling 17/28, parser 0/28. No sentence in the set states an explicit observation date, so interpretation of validity could not be scored.
- Small samples: dates have 13 gold facts, negations 14. Do not rank methods on these.

### The brief's example, row `p-1` (held-out)

"Holdan started at Hooly on 12 January 2026." Gold is `Holdan / joined / 2026-01-12`.
- Parser: no fact. OpenIE: **correct**, status `complete`.
- Slot filling: **wrong** (`Hooly / soc2_audit_start / 2026-01-12`), also status `complete`, confidence 0.638. Extraction confidence does not signal this error. [M]

## 4. Answers

**Q1. Which method recovers the most correct facts missing from `form`?**
None meaningfully. Measured beyond-form facts: OpenIE 3, slot filling 7, union 8, intersection 2. By my review [R] each of them contains exactly **one** correct fact (`head_of_security = Ron LaFlame`) and one uncertain; the rest are wrong. A tie at one, and unverified by a human.
If "missing" is read as "missed by the existing parser", the answer is the union (recall 66.7% vs 22.4%), then slot filling (62.8%) and OpenIE (62.3%), which are not distinguishable.

**Q2. Which method delivers the best factual precision, especially for dates, numbers and negations?**
Intersection has the highest precision (98.2%) but loses recall. Among single methods OpenIE is best (97.4% vs 94.3%, intervals overlap). OpenIE leads on dates (9/9 vs 5/7) and money (15/15 vs 13/14). Slot filling is 100% on quantity (40/40) and better on names (58% vs 37% recall). Neither is good at negation (5/14 and 6/14); both are correct whenever they do flag it.

**Q3. Does combining OpenIE and slot filling outperform the individual methods?**
Not demonstrated. Union adds about 4 recall points over the better single method (66.7% vs 62.8%) and costs 0.5 to 3.6 precision points (93.8% vs 94.3% and 97.4%). All these differences are inside the 95% intervals. Intersection raises precision by under one point over OpenIE (98.2% vs 97.4%) and loses 4 recall points. The two extractors share design and training data, so their agreement is weak evidence of truth: on `p-1387` they agreed on the same wrong subject.

**Q4. Does better extraction provide enough verified evidence to generate 1,000 original true claims?**
No. [M] The safe run (`claim_factory/output/run_main`) makes 411 contract-valid, novel claims: fact 140, compare 200, change 0, at_event 61, relation 10. Feeding in reconstructed facts under a corroboration gate (both methods agree, or the fact is already in that row's form) admitted 501 to 1,668 facts and added **0 claims**: every correct extraction duplicates a fact the graph already holds. The limit is the number of verified, fresh (subject, attribute) values on 29 Oct (150 of 514 fact keys), and change claims, which the engine never accepts as verified.
Runs that reach 956 or exactly 1,000 do so by relaxing truth rules or by pairing combinatorially, and contain at least 121 claims whose text does not match what was verified. **They are not safe and must not be submitted.** A possible safe addition, 424 date-only cross-attribute compares, would give about 835 [E] and is the user's decision.
In the real run, the ~18,000 unlabelled rows cannot pass the "source labelled true" gate, so reconstruction would likely add nothing there either [E].

**Q5. Can the selected approach run offline within 2 CPUs, 6 GiB, a 3 GiB image and 30 minutes?**
Probably yes, with caveats.
- Both extractors are standard-library only, offline, and about 0.25 to 0.27 MB of code and tables [M].
- Measured on 1,897 rows [M]: OpenIE 2.16 s CPU, 25.9 MB peak. Slot filling 2.20 s CPU, 22.5 MB peak. Combine step 1.39 s, 39.5 MB.
- The subagents' own scale tests (single runs, repeated rows, not new text) [M]: OpenIE 20,867 rows in 33.3 s, 67 MB; slot filling 20,000 rows in 39 s, 52.5 MB.
- Extrapolation to ~20,000 rows for the whole OpenIE + slot filling + combine pipeline is roughly 1.5 minutes [E].
- **Not measured:** no Docker image was built (the daemon was not running), no Linux run, no run on a real 2-CPU container. The image size (~150 MB with a slim Python base) is an estimate [E]. Python 3.14 was used; the target container's version is untested.

**Q6. What should be integrated into the NEURON5 production pipeline, and what should be rejected?**
See section 5.

## 5. Recommendation

### Keep
- **The OpenIE-style extractor as the single source of reconstructed candidates.** Highest single-method precision (97.4%), best on dates and money, fewest extras (3), no dependencies. Slot filling is better on names (58% vs 37% recall) and on quantity precision (40/40), and worse on dates and money. None of these gaps is outside the 95% intervals, so this choice rests on the precision-first rule in the brief, not on a demonstrated difference.
- **Use agreement as a trust tier, not a union.** Facts both methods extract (1,424 of the union's 1,663) have 98.2% precision against form (107/109) [M]. Of the union's 8 facts that did not match the form, 6 come from the 239 single-source facts. Keep the slot-filling code as the second opinion, but do not ship the union as one list.
- **The integration point:** `core/graph/builder.py` already runs `parser.parse(row.text)` and stores its output as `UNVERIFIED_CANDIDATE` records with provenance. An adapter that returns the same `ExtractionResult(facts, status, confidence)` is a drop-in seam. Facts then enter the existing `candidate_facts_by_key` and `candidates_by_row` indexes, and `EvidenceResolver` already reports them as `UNVERIFIED_CANDIDATE`, never support. No change to P0 or the graph's trust rules is needed. Do this only with approval; I made no change.
- The `FactRecord.provenance` string (the graph already carries one) should name the method and the agreement tier.

### Reject or hold
- **Never promote reconstructed facts to `VERIFIED_SUPPORT`.** Confidence is not evidence: slot filling returned a wrong `complete` fact on the brief's own example.
- **The `negated` flag on non-boolean facts** (slot filling has 6, all wrong). Use it only for booleans.
- **The relaxed and combinatorial claim runs** (`run_relaxed`, `run_samekind_strict`, `run_max_relaxed_samekind_top1000`).
- **The claim that reconstruction raises the claim count.** It did not.
- **spaCy and Stanford OpenIE:** untested, not rejected on evidence. Revisit only if there is time to run them against the same set.

### Do next, in order of value
1. **Subject recovery from context.** 29% of form facts have a subject that is not in the sentence, and the best method gets 4 of 53. The data is grouped by date and page; carrying the subject from the previous row of the same page is a candidate technique. Untested [U]. It is the largest measured gap.
2. **Human verification** of the 8 beyond-form facts and the worksheet (`evaluation/worksheet/`). Until then "correct new facts" is a model opinion.
3. **A classification test.** Add the candidates to the evidence graph and measure label accuracy on the practice rows with hidden labels. Nothing in this report supports a classification gain.
4. **Reproduce the slot-filling output** (see section 8) and re-score.

## 6. Known problems and honest caveats

- **Slot-filling output is not reproducible from the current tree.** The frozen file has 1,595 facts, the current code gives 1,531. 1,500 unique facts are common, 90 are only in the frozen file and 26 only in the current code. The resource figure for slot filling is from the current code. The frozen file's accuracy was scored; its CPU time was not.
- **Dev numbers are optimistic.** Both tables were fitted on all dev rows. The 15 dev rows in the evaluation set are therefore not a test. The held-out figures in section 3 are the ones to quote.
- **Small, purposive evaluation set.** It over-samples hard cases by design (paraphrase, numeric confusables, implicit attributes), so absolute numbers do not carry over to the whole dataset.
- **Gold is the dataset's `form`, not the truth.** A few form facts may not be stated by their sentence (12 rows carry that concern, e.g. `p-579`, `p-1209`), which affects precision and recall in either direction.
- **Subagent reviews are model judgments.** The extractors' own dev self-checks use a different set and are not directly comparable to the evaluation set: 5-fold CV on the 1,627 dev rows gives OpenIE 96.0% precision and 57.6% recall (all mapped facts; 96.8% and 56.0% for `complete` only), and slot filling 96.3% and 57.6%. These are of the same order as the held-out figures in section 3, which are somewhat higher for recall because the evaluation set is purposive.
- **The claim backtest uses practice rows as truth** and may be biased. 40 of 61 at_event claims depend on how the referee resolves two rescheduled events.
- **Resource numbers are from a busy Windows laptop**, not the competition container.
- **Classification:** not tested. **Docker:** not built.

## 7. Where everything is

| What | Where |
|---|---|
| Common format, validator, split, frozen hashes | `experiments/shared/` |
| OpenIE: code, facts, reports | `experiments/openie/` (`output/facts.jsonl`, `REPORT.md`, `FAILURES.md`, `DEPLOYMENT.md`) |
| Slot filling: code, facts, reports | `experiments/slot_filling/` (same, plus `output/attribute_coverage.csv`) |
| Evaluation harness, set, worksheet, results | `experiments/evaluation/` (`results/final/summary.md`, `results/resources_final.json`) |
| Claim factory: code, runs, report | `experiments/claim_factory/` (`FEASIBILITY_REPORT.md`, `output/run_main`) |
| My review of beyond-form facts | `experiments/shared/coordinator_review_beyond_form.csv` |
| Earlier status | `experiments/HANDOFF.md` (superseded by this file) |

Reproduce the comparison:
```
$env:PYTHONUTF8='1'
py experiments/evaluation/combine.py
py experiments/evaluation/measure_resources.py --methods baseline openie slot_filling combined --repeats 3 --affinity --out experiments/evaluation/results/resources_<new>.json
py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_<new>.json --out experiments/evaluation/results/<new>
```

## 8. Housekeeping before any commit

- Remove scratch: `openie/tools/_attrs_dump.txt`, `openie/spacy_install.log`, `slot_filling/_dbg.py _fn.py _row.py _t*.py`, `claim_factory/_x.py`, `evaluation/_scratch/`.
- Keep `evaluation/_scratch/dump.txt` and `selected.txt` (held-out gold) out of any shared upload.
- `evaluation/results/resources_final_runs/` holds the measured runs' output; it is safe to delete.
- Add `experiments/shared/_heldout/` to ignore rules if the repository is ever made public.
