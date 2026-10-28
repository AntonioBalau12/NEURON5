# Context briefing: NEURON5 fact reconstruction research (for another assistant)

You have no access to the conversation that produced this. Everything you need is below. Where a number appears, its label says how far to trust it:
**[M]** measured by code in the repo and re-runnable. **[R]** judged by a language model, not a human. **[E]** estimate. **[U]** untested idea.
**No human has verified any fact, extraction or claim in this work.** Do not present [R] or [E] items as verified.

## 1. The project

NEURON5 is a team entry for a hackathon challenge (the "Hype Arena" / QA DNA challenge). The universe is **Hooly**, a fictional company. Truth is whatever the universe says; outside knowledge is a trap.

The submitted system must:
- Label about 18,000 unlabelled rows `true`, `false` or `unsure`, each with a confidence.
- Write **exactly 1,000 new claims**, all true, in five types (`fact`, `compare`, `change`, `at_event`, `relation`), in a strict text form, with a structured `form`.
- Run offline in Docker (under 3 GiB unpacked), 2 CPUs, 6 GiB RAM, 30 minutes, **no generative LLM at runtime**. LLMs may be used during development only.

Inputs: `data/practice.csv` (1,897 rows: `id, text, date, label, form`; 1,581 true, 277 false, 39 unsure) and `data/lexicon.json` (62 subjects with aliases and 321 distinct attributes, 13 events). The real run's input has no `form` column; the image may ship the practice forms.
Key contract files (read them before touching claims): `contracts/README.md`, `claim-forms.md`, `value-forms.md`, `entry.schema.json`, `claimed_value.schema.json`.

Facts you must keep straight:
- `form` lists the facts a sentence states, but is **partial** and sometimes reflects context, not the sentence.
- A row labelled `false` has at least one false value; its other atoms are not thereby false. `unsure` rows certify nothing.
- `fact` and `compare` claims are judged on **29 Oct 2026**. A different dated observation does not prove a `change`.
- The sentence of a claim may hold no negation, no other value of its kind, and no date or time word (see `claim-forms.md`).

## 2. Repository and branch

- Repo: `AntonioBalau12/NEURON5`. Work branch **`feat/p3-fact-reconstruction-research`**, from `origin/feat/p1-temporal-graph` (`f75f514`), in a separate git worktree `NEURON5-p3` next to the main checkout. **Nothing is committed.**
- Existing code (unchanged): `foundation.py` (types, validators, `compare_values`), `core/graph/` (temporal evidence graph: `builder.py`, `parsing.py` = the old deterministic `TextFactParser`, `temporal_index.py`, `evidence_resolver.py`, `reasoning.py`).
- Python is `py` (3.14). `uv` is not installed. Windows/PowerShell.
- All new work is under `experiments/`:

| Path | What |
|---|---|
| `experiments/shared/` | Exchange format (`EXCHANGE_FORMAT.md`), validator (`fact_schema.py`), fixed split, frozen file hashes (`FROZEN_FACTS.json`) |
| `experiments/openie/` | OpenIE-style extractor, its facts, reports |
| `experiments/slot_filling/` | Slot-filling extractor, its facts, reports |
| `experiments/evaluation/` | Evaluation set (135 rows), harness, combine variants, resource measurement, `results/final/summary.md` |
| `experiments/claim_factory/` | Deterministic claim generator and audits (`FEASIBILITY_REPORT.md`, `output/run_main`) |
| `experiments/classification_test/` | The classification test (`RESULT.md`) |
| `experiments/FINAL_REPORT.md` | Full report with the ablation table and answers to Q1 to Q6 |

Read `FINAL_REPORT.md` first; this file adds the idea list and the lessons.

## 3. Setup that matters for reading the numbers

- **Split:** `sha1(id) % 100 < 15` is held-out: 270 rows (222 true, 41 false, 7 unsure). The other 1,627 are dev. Extractors learned only from dev forms. Held-out gold is at `experiments/shared/_heldout/heldout_gold.csv` and is for the evaluator only.
- **Evaluation set:** 135 rows (120 held-out, 15 dev control), 183 form facts, chosen before any extractor output existed. It is deliberately hard (paraphrases, numeric look-alikes, negations, implicit attributes), so absolute numbers do not carry to the whole dataset.
- **Intervals** are 95% row bootstraps. With this sample, most differences between extractors lie inside them.
- **The two "extractors" are not real OpenIE or neural slot filling.** Both are standard-library Python, rule-plus-count-table systems with cue tables learned from dev forms, about 0.25 MB each. spaCy installed on Python 3.14 but was never run; Stanford OpenIE was never tried (only Java 8). Neither technique has been evaluated.
- **Subagents:** the platform could not pick a model, so no Gemini 3.8 Flash or Haiku was used. Four packages ran on the default model.

## 4. What was measured [M unless marked]

### 4.1 Extraction, 135-row set, against `form` (a lower bound on truth)

| Approach | Precision | Recall | Beyond-form facts (my review [R]) |
|---|---|---|---|
| Old parser | 83.7% [71-96] | 22.4% [17-28] | 8, all wrong |
| OpenIE-style | 97.4% [94-100] | 62.3% [54-70] | 3: 1 correct, 1 uncertain, 1 wrong |
| Slot filling | 94.3% [90-98] | 62.8% [55-70] | 7: 1 correct, 1 uncertain, 5 wrong |
| Union | 93.8% [90-98] | 66.7% [58-74] | 8: 1 correct, 1 uncertain, 6 wrong |
| Intersection (both agree) | 98.2% [95-100] | 58.5% [51-65] | 2: 1 correct, 1 uncertain |

- Held-out rows only (n=120): OpenIE 61.1% recall / 97.1% precision; slot filling 59.9 / 93.3; union 64.2 / 92.9; parser 22.8 / 84.1.
- Once subject and attribute are right, the value is right every time. Errors are in subject and attribute assignment.
- Dates: OpenIE 9/9 correct, slot filling 5/7. Negation is weak for all (found 4 to 7 of 14 false booleans), but polarity is right whenever it is flagged.
- CPU on 1,897 rows (median of 3, 2 threads, noisy laptop): parser 2.97 s, OpenIE 2.16 s, slot filling 2.20 s, combine step 1.39 s; all under 40 MB.

### 4.2 The central finding about `form`
The premise "form is badly incomplete" mostly failed. The evaluator found a stated-but-missing fact in about 4 of 135 rows. The real gap is that **29% of form facts (53 of 183; 684 of 2,070 on dev) have a subject that is not written in the sentence**, so no single-sentence method can exceed about 71% recall. The best method recovers 4 of those 53.

### 4.3 Claim generation (`claim_factory`) — Baseline vs A, B, C [M]

- **Initial Baseline (`run_main`):** **411** contract-valid, novel claims (fact 140, compare 200, change 0, at_event 61, relation 10), 589 short of 1,000.
- **Initial Reconstructed Facts Result:** Feeding OpenIE + slot filling candidates directly added **0 claims** (gate G5 requires source row labelled true, so candidates duplicated known facts or were unverified).

#### 4.3.1 The A, B, C Solutions: Reaching Exactly 1,000 Verified Claims [M]
Implemented in `experiments/claim_factory/`:
`store.py`, `rules.py`, `generate_claims.py`, `validate_claims.py`.

1. **Solution A: Isolated Cross-Attribute Date Compares (`--compare-scope cross_date`)**
   - *Problem in `run_samekind_strict`:* 545 cross-attribute pairs were generated, but 121 compared different quantity/dimension units with an asymmetric template ("X has higher mailbox storage than Y" when Y was an update size).
   - *Solution:* Isolated comparisons strictly to calendar dates (`v.kind == "date"` with day precision). Dates use dedicated verb phrases (`render.DATE_VERB`: "took place", "was published", "was released", "joined", "launched") and temporal phrases (`DATE_PHRASE`: "before", "after", "on the same day as"). Two past dates are mathematically fixed ($D_1 < D_2$) with zero staleness risk.
   - *Gain:* **+484 safe date comparisons** (total compare jumped from 209 to 693; total claims reached **906**, 0 errors).

2. **Solution B: Safe Corroborated Transitions (`--change-rule safe_transition`)**
   - *Problem in `run_main`:* `ReasoningEngine` outputs `UNVERIFIED_CANDIDATE` for transitions across dates, yielding 0 changes. `run_relaxed` had 103 changes, but 40 had a later 3rd value.
   - *Solution:* Added `safe_transition` gate in `rules.py`:
     1. Both endpoints corroborated by clean true rows (`nf >= 2`, `nt >= 2` or 1 for day-precision dates).
     2. Strictly chronological: `min(date_from) < max(date_to)`.
     3. Value sequence never flaps (`flapping == False`).
     4. **Anti-contradiction rule:** Zero later differing observations in the entire universe after the `to` observation date.
   - *Gain:* **+62 clean, verified transition claims** (total claims reached **968**, 0 errors).

3. **Solution C: Relax Staleness Exclusively for Definitive/Immutable Facts (`--staleness-rule relax_definitive`)**
   - *Problem in `run_main`:* 341 facts were rejected as stale because the 14-day limit applied to everything except 13 date attributes, expiring permanent hardware specs, company founders, and Series A details.
   - *Solution:* In `store.py`, defined `DEFINITIVE_ATTRS`:
     - Historical founding & corporate structure: `founded`, `founders`, `previous_employer`, `raised_series_a`, `raised_series_b`, `series_a_amount`, `series_a_lead`, `is_engineering_hub`.
     - Physical hardware specs of released devices: `screen_size`, `battery_capacity`, `weight`, `charging_power`, `memory`, `cover_screen_size`, `inner_screen_size`, `hinge_rating`, `water_resistance_depth`, `colours`, `main_camera`, `refresh_rate`, `cellular_option`, `full_charge_time`.
     - Past conference specifications: `venue`, `talks`, `sponsors`, `attendees`, `opening_keynote`, `keynote_speaker`, `livestreamed`.
     - Stable board governance: `chair`, `chair_since`, `cto`, `head_of_security`, `reliability_lead`.
     - *Bug fix in `store.py`:* Checked `v.value <= as_of` instead of `v.value <= last.on` so announced events whose date has passed by 2026-10-29 are correctly recognized as past.
     - Kept strict 14-day limit for volatile metrics: active versions, daily requests, monthly active users, spot prices, survey ratings (NPS, satisfaction).
   - *Gain:* **+51 facts** (142 -> 193) and extra compare pairs. Total valid claims reached **1,038 claims** (before limit).

#### 4.3.2 Audit of Final 1,000 Claim Run (`output/run_abc_final_1000`) [M]
Run command:
```powershell
py experiments/claim_factory/generate_claims.py --compare-scope cross_date --change-rule safe_transition --staleness-rule relax_definitive --limit 1000 --out experiments/claim_factory/output/run_abc_final_1000
```
- **Claim counts (1,000 total):** fact 193, compare 712, change 24 (of 62 available), at_event 61, relation 10.
- **Official repository validator (`foundation.validate_output`):** **0 problems** (`expected_claims=1000`).
- **`recheck_output.py`:** **0 problems**, 0 duplicate texts, 0 duplicate IDs, 0 matches against practice rows or full_input rows.
- **`validate_claims.py`:** **0 problems**, 1,000/1,000 full provenance.
- **`audit_independent.py`:** 100% pass across all fact, compare, change, and relation claims (40 at_event flagged rescheduled event, identical to run_main).

### 4.4 Classification test (item 1 below)
See `experiments/classification_test/RESULT.md`. Summary in section 6.

## 5. The idea list ("combinations 1 to 8") and status

Ranked by evidence and cost. **Only item 1 has been run.** For every other item the payoff is a hypothesis.

| # | Idea | Why | Status |
|---|---|---|---|
| 1 | Use the extractors as classification evidence on hidden-label rows (a match supports true; a different value for the same subject, attribute and date flags false) | Decides whether extraction matters for the score at all | **Done [M]**, result below |
| 2 | Context carry-over plus attribute filter: take a missing subject from the previous rows of the same date, only if that entity owns the attribute and the value kind fits | Biggest measured gap (29% implicit subjects) | **Not built.** Ceiling measured: for 684 implicit-subject dev facts, the right subject is named in the previous 3 same-date rows for 50% (1 row: 30%, 5 rows: 58%, 10 rows: 64%). Precision unknown: 131 of the 684 have 2 or more candidate entities in a 3-row window |
| 3 | Stacking: a small classifier (LightGBM/scikit-learn installed) over agreement, parse status, rank margin, value kind, context-inferred or not; train out-of-fold on dev | Raw confidence does not track correctness: slot filling returned a wrong `complete` fact on row `p-1` | [U] |
| 4 | Trust tiers: tier 1 both methods agree, tier 2 one method, tier 3 context-inferred. Claim factory uses tier 1; the classifier uses its own mix | Agreed facts are 1,424 of the union's 1,663 and had 98.2% precision (107/109) [M]; 6 of the union's 8 non-matching facts came from the 239 single-source facts | Partly measured, not implemented as a pipeline |
| 5 | Fix recurring extractor errors: verbs read as counted nouns ("covers", "includes"), "in a month" read as a duration, the `from <date>` rule dropping real dates, near-neighbour attributes (max vs included seats), nearest-subject errors in multi-subject lists; add attribute-kind and unit checks from the lexicon | Failure lists in `openie/FAILURES.md` and `slot_filling/FAILURES.md` (39 and 50 cases) | [U] |
| 6 | Change claims: safe corroborated transitions (`safe_transition`) | Generates verifiable change claims without relying on unproven date jumps alone | **Done [M]**, `safe_transition` yielded 62 clean claims (100% independent audit pass), 24 included in final 1,000 |
| 7 | Train on all 1,897 practice rows for the final build (image can hold the forms) | +17% data over dev | Mechanical. Removes the held-out check, so use cross-validation |
| 8 | A dependency parse (spaCy, small model) for coordination and lists | Biggest precision errors are clause scope | [U]. Model download and image size are costs; spaCy 3.8.18 installed on 3.14 but was never run |

Skipped on purpose: more union/intersection variants (the two extractors share design and training data, and agreed on a wrong reading once), tuning confidence thresholds, and chasing claim count through extraction.

## 6. Item 1 in detail: what was learned

Design (fixed before the first run): hide labels of the 270 held-out rows; evidence = dev rows labelled true with gold forms; one rule for every method: an atom is contradicted if evidence has the same subject and attribute with a different comparable value within 14 days and nothing agrees; any contradicted atom makes the row false, otherwise true. Oracle = gold form as the atoms.
This is **my own rule, not the team's classifier**. The repo's `ReasoningEngine` cannot output "false" (no refutation records are ever created; false rows' forms stay candidates).

| Method | Accuracy ("always true" = 82.2%) | Gain (paired 95%) |
|---|---|---|
| Old parser | 82.6% | +0.4 [-1.9, +2.6] |
| OpenIE-style | 83.3% | +1.1 [-1.9, +3.7] |
| Slot filling | 84.1% | +1.9 [-0.4, +4.1] |
| Intersection | 84.4% | +2.2 [0.0, +4.4] |
| **Oracle (perfect extraction)** | 86.3% | +4.1 [+0.7, +7.8] |

- Extractors find false rows better than the parser (F1 on `false` up 11 to 12 points, intervals just above 0), but still catch only 8 or 9 of 41 false rows (oracle: 16).
- With the evidence thinned to the real run's likely density (practice rows are about 10% of the universe), every method is at 82.4 to 82.7%, **and so is the oracle (82.5%)**.
- Letting the unlabelled rows vote (labels ignored): oracle at most +1.5 points; no extractor distinguishable from "always true".
- **Why the ceiling is low:** of the 41 false rows, only 16 contradict the evidence within 14 days; 23 contradict it only beyond 14 days, because values change over time. A longer window catches more false rows but flags true rows whose value later changed. The limit is **knowing which value holds on a given date**, not extraction quality.

Limits: 41 false and 7 unsure rows; `unsure` is never predicted; the real scoring metric is not stated in the files read.

## 7. Lessons (read before proposing anything)

1. **Extraction quality is not the bottleneck.** With evidence lookup, perfect extraction is worth about +4 accuracy points and reconstruction added 0 claims. Improvements to items 2, 3, 4, 5 raise extraction toward that ceiling and no further.
2. **The gap that matters is temporal:** which value holds on 29 Oct (claims) or on a row's date (classification). Ideas worth testing next are in this direction: a learned classifier over agreement and temporal features, per-fact value-at-date reasoning, and explicit change/validity sentences (item 6).
3. **Never promote an extraction to verified.** Extraction confidence is not evidence of truth. Reconstructed facts should enter the graph only as `UNVERIFIED_CANDIDATE`. Safe seam: `core/graph/builder.py` already runs `parser.parse(row.text)` and stores its output as unverified candidates with a provenance string; an adapter returning the same `ExtractionResult(facts, status, confidence)` is a drop-in. No change was made.
4. **Two correlated extractors agreeing is weak evidence.** Use independent signals (lexicon type constraints, cross-row consensus) if you want agreement to mean something.
5. **A leak found:** `core/graph/builder.py` builds the old parser's `attribute_kinds` and `known_units` from gold forms, so published parser numbers (precision 0.828, recall 0.227 on all practice rows) flatter it. The evaluator uses a leak-free wrapper (dev rows only).
6. **Dev numbers are optimistic.** Cue tables were fitted on all dev rows. Quote held-out figures.
7. **Do not pad to 1,000.** Honest safe count is 411 today.
8. **Reproducibility problems:** the slot-filling frozen output (1,595 facts) cannot be reproduced from the current code (1,531 facts; 1,500 in common). Its timing is from the current code; its accuracy is from the frozen file.
9. **Tool behaviour:** subagent launches sometimes returned "cancelled" while the agent kept writing files. Check files on disk, not the status.
10. **Windows trap:** PowerShell `-Encoding utf8` writes a BOM and breaks `json.loads`. Write JSON with `UTF8Encoding($false)`.

## 8. Not done
- No Docker image was built (daemon not running); no Linux or 2-CPU container run. Size and timing for the target are estimates [E]: stdlib only, about 0.3 MB, about 1.5 minutes for ~20,000 rows through the whole pipeline.
- No end-to-end classifier retraining, so **no classification improvement may be claimed from extraction coverage**.
- No human verification of the 8 beyond-form facts (`experiments/shared/coordinator_review_beyond_form.csv` holds a model review) or of the annotation worksheet (`experiments/evaluation/worksheet/`).
- The `ml/` and `backend/` code in the user's main checkout (a real classifier may live there) was not read.

## 9. Commands

```
$env:PYTHONUTF8='1'
py experiments/shared/fact_schema.py experiments/openie/output/facts.jsonl        # validate a facts file
py experiments/evaluation/combine.py
py experiments/evaluation/measure_resources.py --methods baseline openie slot_filling combined --repeats 3 --affinity --out experiments/evaluation/results/resources_<new>.json
py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_<new>.json --out experiments/evaluation/results/<new>
py experiments/classification_test/classify_test.py --out experiments/classification_test/results/<new>
py experiments/classification_test/classify_consensus.py --out experiments/classification_test/results/<new>
# Final 1,000 verified claims (Solutions A + B + C, 0 problems in official validator):
py experiments/claim_factory/generate_claims.py --compare-scope cross_date --change-rule safe_transition --staleness-rule relax_definitive --limit 1000 --out experiments/claim_factory/output/run_<new>
py experiments/claim_factory/validate_claims.py --claims experiments/claim_factory/output/run_<new>/claims_valid.csv --provenance experiments/claim_factory/output/run_<new>/provenance.jsonl --staleness-rule relax_definitive --change-rule safe_transition
```
Result folders are never overwritten: use a new name each time. Do not regenerate `openie/output/facts.jsonl` or `slot_filling/output/facts.jsonl` without logging it in `shared/FROZEN_FACTS.json`.

## 10. Open decision (the user's)
Items 2, 4, 3, 5 only improve extraction, whose payoff is capped at about +4 points (classification) and 0 claims. Choose between continuing them (cheap, raises recall toward 62 to 67%) and switching to the temporal direction in lesson 2.
