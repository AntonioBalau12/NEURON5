# Claim factory: feasibility report

Labels: **[measured]** computed by code in this repo and re-runnable, **[estimate]** derived from measurements by reasoning, **[unverified]** not checked against the referee or humans.
Nothing here is human-verified. Every claim comes from `data/practice.csv` and its gold forms (the only labelled rows available locally). As-of date 29 Oct 2026; the last practice row is dated 28 Oct 2026.

## 0. Bottom line

* The strict run (`output/run_main`) holds **411 contract-valid, novel claims**: fact 140, compare 200, change 0, at_event 61, relation 10. **589 short of 1,000.** [measured]
* The repository validator `foundation.validate_output` reports **0 problems** on it; no claim text equals any practice or shared-input row text. [measured, section 3]
* My own hand review of 42 of those claims found 0 clearly wrong, 10 uncertain (2 facts, 8 at_event). Backtest of the "value still holds" rule gives 96.6% agreement; expected wrong claims in run_main are roughly **4 to 10 of 411** [estimate, section 1].
* The runs that do reach 1,000 do it by relaxing truth rules or by combinatorial pairing, and are **NOT SAFE** (section 2). **Padding to 1,000 with unsafe claims was not done.** The deliverable is `run_main` (411), nothing was added to it.
* Reconstructed facts (OpenIE, slot filling) add **0** claims in every variant tried (section 4). [measured]

## 1. Audit of run_main

### Counts (funnel per type) [measured, `output/run_main/rejections_summary.json`]

| type | candidates generated | verified by evidence rules | contract-valid (render + form + lexicon + text checks) | novel and final |
|---|---|---|---|---|
| fact | 514 | 150 | 145 | **140** |
| compare | 523 | 200 | 200 | **200** |
| change | 325 | 0 | 0 | **0** |
| at_event | 90 | 62 | 61 | **61** |
| relation | 50 | 15 | 10 | **10** |
| total | 1,502 | 427 | 416 | **411** |

The 5 fact candidates lost at the last stage were rejected because their text equalled an input row (`novelty:text_equals_an_input_row` 5). Closest claim to any input row: Jaccard 0.9 ("Hooly Q4 2025 Results was published on 28 January 2026." vs p-1300); 3 claims above 0.8, 0 equal (`run_main/novelty_risk.json`).

### Rejection reasons (all reasons, counts of candidate/reason pairs) [measured]

| reason | count |
|---|---|
| compare: a side not verified | 501 |
| fact: stale (last support older than 14 days, not an immutable past date) | 341 |
| change: engine only has a "candidate" (dates of observations do not prove a transition) | 298 |
| fact: blocked by a later false/unsure row stating another value | 64 |
| fact: insufficient corroboration | 26 |
| relation: no same-day link + target observation | 26 |
| change: boolean change not generated | 22 |
| at_event: subject is the event itself | 14 |
| fact: no verified support | 12 |
| compare: values incomparable / kind not comparable (version, name) | 7 / 4 |
| at_event: event-day observation unclean (past/future wording) | 7 |
| relation: name-valued target fact excluded | 7 |
| fact: latest support has an op ("over", ...) | 6 |
| fact: latest support has a tense cue (was, planned, next, ...) | about 39 across 19 cue variants |
| render: name value not in lexicon | 6 |
| render: relation link word ungrammatical in the frame ("chairs", "run_by") | 5 |
| change: endpoints equivalent | 5 |
| at_event: date-valued event fact excluded | 5 |

### The three rules you asked about

**Fact: "value still holds on 29 Oct 2026".** [measured + estimate]
Nothing in the data proves persistence. The rule accepts the latest true-row value only when the latest observation has no past/future wording, no later false/unsure/conflicting row states another value, and the observation is at most 14 days before 29 Oct (past one-time event dates such as `joined`, `launched` have no age limit).
* Of the 140 facts, 36 are immutable past dates and 104 are mutable. Age of the latest support: 39 at 0-3 days, 10 at 4-7, 58 at 8-14, 33 older (immutable dates). 41 facts rest on one true row; 34 of them are mutable.
* `backtest.py` replays the rule on every earlier date where a true row states the fact: default rule accepts 319, 308 agree, 11 contradicted = **96.6% agreement**; by age 0-7 days 97.5%, 8-30 days 94.1%. A 30-day window gives 90.6%, 60 days 87.8%, no limit 77.7%. The truth on the target date is again a practice row, so this is an agreement rate on the same sample, not proof; selection bias is possible [unverified].
* Applying 3.4% to 4% (mutable only) to 104 mutable facts gives about **4 wrong facts** [estimate]. The riskiest group is 17 facts: version / stable release / latest release / cadence (`fact-0011, 0019, 0020, 0036, 0049, 0052`), cumulative sold counters (`0065, 0067, 0070, 0072`) and single-row facts that are 8 or more days old (`0013, 0119, 0123, 0128, 0134`, and others). Example: Hooly Chrome "stable version 72.0" was seen on 20 Oct with a 4-week cadence and a 29 Sep release, so a next stable around 27 Oct is plausible. The backtest itself lists an Android 17.0 to 17.1 contradiction. Dropping those 17 would cost 17 claims.

**Change: "different dated observations do not prove a change".** [measured]
The engine (`core.graph.ReasoningEngine`) answers every change as `UNVERIFIED_CANDIDATE`, so strict mode emits **0 change claims** (298 candidates refused for that reason). `run_relaxed` admits 103 pairs where both endpoints are corroborated by two clean rows (a date endpoint needs one) and the value sequence does not flap. The contract wording ("it held `from`, and at a later date `to`") is literally met by such a pair, but the engine does not accept it and I could not verify it. Of 9 change claims I read from run_relaxed, 5 look plausible and 4 are uncertain (a different statistic or a different survey edition); none clearly wrong. The independent re-derivation flags 40 of the 103 because a later row shows yet another value (then A to B still happened, but I mark it "uncertain" rather than pass).

**Compare.** [measured]
200 claims: 137 date comparisons (launch / join / event dates, past and immutable) and 63 amount comparisons (percent 15, money 21, quantity 21, duration 6), all same attribute, both sides accepted by the fact rule. The independent re-derivation from raw forms reproduces all 200 orderings. 12 of the 63 amount comparisons have a side with more than one true value over time (exposure to the 3-4% drift); quarterly results figures are static. All 10 compares I read were true and their texts satisfy the compare table (left subject first, one phrase, no value or number, dates only with `before`/`after`).

### Hand review (own review, not human-verified) [measured as a review, judgement unverified]
42 run_main claims read with provenance (fact 12, compare 10, at_event 10, relation 10; no change exists in run_main), plus 9 change claims from run_relaxed. Details: `output/audit_run_main/review_notes.md`.

| type | read | clearly wrong | uncertain | note |
|---|---|---|---|---|
| fact | 12 | 0 | 2 | 0134 single row at age 14; 0065 cumulative counter |
| compare | 10 | 0 | 0 | |
| at_event | 10 | 0 | 8 | all at rescheduled events, see below |
| relation | 10 | 0 | 0 | |
| change (run_relaxed, not run_main) | 9 | 0 | 4 | |

At-event dependency [measured]: 40 of the 61 at_event claims are at two events whose date was restated (Hooly Cloud Next 2026: 2 Jun in one early true row, 9 Jun in four later true rows and in a row dated 9 Jun; Made by Hooly 2026: 21 Apr in one row dated 18 Feb, 28 Apr in later true rows, with product rows dated 28 Apr). The factory uses the last date. If the referee resolved the earlier date, these 40 would be wrong. [unverified]

Relation: a claim is true when the fact held the value while the link named the subject. The three "reliability lead of Hooly Cloud has a team size of 4 / 11 / 17 engineers" are three values of one changing fact, each stated by true rows while Holdan held the link, so each is true under that rule. [unverified against the referee]

Independent check [measured]: `audit_independent.py` re-derives every claim from the raw forms of all rows (no `core.graph`, no store). Result for run_main: fact 140/140 pass, compare 200/200 pass, relation 10/10 pass, at_event 21 pass and 40 flagged "rescheduled event" (not failed). Details: `output/audit_run_main/audit_independent.json`. It cannot see anything outside the practice sample.

## 2. The other runs, and why not to trust the relaxed ones

All use the same evidence; they differ only in the parameters below. Counts [measured]; safety judgement is mine [unverified].

| run | parameters | claims | what it trades | safe? |
|---|---|---|---|---|
| run_main | max-age 14, min-support 1, engine change, engine relation, same-attribute compares | 411 | baseline | yes, with the caveats above |
| run_highprecision | max-age 7, min-support 2 | 270 (fact 59, compare 140, at_event 61, relation 10) | fewer facts, higher precision (backtest 97.7% at min2/7d) | yes, safer subset of run_main |
| run_relaxed | `--change-rule corroborated --relation-rule stable` | 518 (fact 140, compare 200, change 103, at_event 61, relation 14) | adds 103 changes and 4 relations that **the engine does not verify** | **NOT SAFE as is.** The extra 107 claims are plausible but unproven. 40 changes have a later third value, 3 of the 4 extra relations fall outside the link rows. Use only if the referee is known to accept two-observation changes. |
| run_samekind_strict | run_main rules plus `--compare-scope same_kind` | 956 (compare 745) | adds 545 cross-attribute compares | **Partly unsafe.** 424 compare two dates and read correctly but are combinatorial. 121 compare amounts of different attributes while the text names only the left attribute ("Hooly Gmail has higher mailbox storage than Hooly Android 17" is verified against Android 17's *update size*; "Hooly Q1 2026 Results has higher cash than Hooly Q2 2026 Results" is verified against Q2's *guidance*, and read literally the cash claim is false). Without those 121: 835 (arithmetic, not a run). |
| run_max_relaxed_samekind_top1000 | `--change-rule corroborated --relation-rule stable --compare-scope same_kind --limit 1000` | 1,000 (fact 140, compare 745, change 44, at_event 61, relation 10) | all of the above, then trimmed to 1,000 by confidence | **NOT SAFE. It reaches 1,000 by relaxing the truth rules and by combinatorics**, contains the 121 text/form-mismatched compares, and `--limit` dropped about 63 of the lower-confidence relaxed claims. Do not submit. |
| run_synthetic_extra | main rules plus 19 hand-made synthetic facts | 415 | test of the extra-facts path only | test artifact, not evidence |

Looser parameters in `sensitivity.json` [measured]: age 30 days gives 486 claims (backtest agreement 90.6%), age 60 days 547 (87.8%), no age limit 768 (77.7%), relaxed + age 30 days 593, loosest 608. **Even the loosest single-attribute setting stays under 610**, so the 1,000 mark is not reachable by loosening freshness or change rules alone, and the loose settings already carry 10 to 22% expected falsehood.

## 3. Re-validation of run_main [measured]
`py experiments/claim_factory/recheck_output.py output/run_main/claims_valid.csv ...` (output: `output/audit_run_main/recheck_output.json`):
`foundation.validate_output(expected_claims=411)` problems **0**; claims equal to a practice row text (normalised and exact) **0**; equal to a shared `full_input.csv` text **0**; duplicate texts 0, duplicate ids 0.
`validate_claims.py` (four layers: official validator, schema/lexicon/text checks, novelty/dups, truth re-check): 0 claims with any problem, 0 without provenance (`audit_run_main/validate_claims_report.json`). Validating against `expected_claims=1000` reports 1 problem, which is only the count.

## 4. Reconstructed facts [measured]
`experiments/shared/FROZEN_FACTS.json` exists. The sha1 of `openie/output/facts.jsonl` (6c7bd87d...) matches the frozen record; the slot-filling file matches too (a60e086b...). Both validate with `fact_schema.py` (2,184 and 1,595 facts, 0 invalid).

Settings: gates G1-G7 of `extra_facts.py` (schema + exact span, `parse_status = complete`, confidence threshold, negation handling, source row labelled `true`, no op / validity end / past-future qualifier, source row in graph). Corroboration rule (new mode `agree_or_form`): the fact is already a verified form fact of the same row, **or** two different methods agree on the same row, subject, attribute and value. The cross-row refresh rule is not used. (I added only the `agree_or_form` choice to `extra_facts.py` and `generate_claims.py`.)

**Threshold 0.7**, justified by measurement (`output/audit_run_main/extra_fact_precision_vs_gold.json`): OpenIE confidence never reaches 0.8 (max 0.77), so the default 0.8 would admit nothing from it. Matches against the gold form of the same row (true rows, complete, not negated): OpenIE 97.6% at any threshold, 98.6% at 0.7; slot filling 97.2% at any threshold, 97.8% at 0.7, 98.2% at 0.8. The threshold changes precision by about 1 point either way; the gate that matters is the corroboration rule.

| run | facts in file | refused (main reasons) | admitted | of which new to the graph | extra valid claims over run_main |
|---|---|---|---|---|---|
| run_extra_openie | 2,184 | low confidence 831, unmapped 687, ambiguous 30, source not true 117, past/future qualifier 11, no corroboration 7 | 501 (all by row_form) | **0** | **0** |
| run_extra_slotfill | 1,595 | source not true 255, past/future qualifier 25, op 20, ambiguous 29, partial 27, low confidence 39, negation 8, no corroboration 27 | 1,165 (all by row_form) | **0** | **0** |
| run_extra_both (merged file `output/extra_inputs/openie_plus_slot_filling.jsonl`) | 3,779 | as above | 1,668 (row_form 1,666, two_methods 939, 937 by both) | **2** | **0** |
| run_extra_both_anyrule_diagnostic (adds cross_row) | 3,779 | | 1,676 (cross_row 718) | 8 by cross_row only + 2 | **0** |

Per rule, run_extra_both: row_form 1,666 admitted; two_methods 939 admitted, of which 937 were also in a form and 2 were new; cross_row (diagnostic run only) 718.

Why 0: both extractors ran only on practice rows, and every practice row already carries a gold form that the graph holds, so correct extractions duplicate facts that are already there. The only 2 new facts are one sentence, "Hooly has 12 customers on Hooly Workspace Enterprise" (p-1387), read by both methods as `Hooly paying_customers = 12`. The gold form says `Hooly Workspace Enterprise customers = 12`, so **both methods agreed on a wrong reading**; two extractors are not independent evidence. The claim for that key was rejected anyway because later false rows state other values. Real unlabelled rows (about 18,000) cannot pass gate G5 (source labelled true) at all, so under this rule extra facts could add nothing there either [estimate].

## 5. What limits the count, and distance from 1,000

* Limiting factor [measured]: the number of (subject, attribute) pairs with a verified, still-fresh value on 29 Oct. There are 514 fact keys, **150** pass; 341 rejections are for staleness and 64 for a later conflicting false row. Compare is quadratic in that number within one attribute (523 pairs generated, 200 valid, 501 side rejections), at_event is capped by the 4 events with a confirmed day (Made by Hooly 2026 32 claims, Hooly I/O 2026 11, Gemini Launch Night 10, Hooly Cloud Next 2026 8; 61 of 90 candidates), relation by link and target facts observed on the same day (10 of 50), and change is capped at 0 by the engine.
* Distance: run_main **589** short (41% of target missing). run_highprecision 730 short. run_relaxed 482 short. [measured]
* Reaching 1,000 safely would need roughly 2.4 times as many verified fresh facts, or an engine-verified change type. [estimate]
* Timing [measured, one machine, Python 3.14]: run_main 9.2 s in total (graph build 5.5 s, generation about 0.2 s, contract checks 1.7 s, official validator 1.7 s); other runs 10 to 28 s; extra-fact runs 8 to 14 s. Time is not a constraint. For the real ~18,000 rows the cost is dominated by extraction, which I did not run [unverified]; graph build scales roughly linearly with rows [estimate].
* Evidence base: practice rows only, forms are gold. A real run on form-less rows would need a fact extractor whose output passes the same gates; its precision (97 to 98% against the gold forms above) is not good enough to skip the corroboration gates.

## 6. What would unlock more claims [estimate unless stated]

1. **Explicit validity statements** ("still", "as of today", `valid_from`/`valid_to`) turn a stale observation into an engine-verified one. Staleness is the single largest fact rejection (341). Raising the age limit adds +62 facts at 30 days and +108 at 60 days [measured, sensitivity.json] but at 91% / 88% agreement.
2. **Explicit "went from A to B / up from A" sentences** (a single sentence stating both values) would make a change claim verifiable without relying on dates; today 298 change candidates are refused.
3. **Fresh restatements of mutable facts** (rows dated 25 to 28 Oct for versions, counters, prices): none exist beyond what the practice sample holds.
4. **More event-day rows** for events whose date is confirmed: only 4 events yield at_event claims; 14 candidates are lost because the subject is the event itself.
5. **Entities missing from the lexicon** (6 name values not rendered): an extended lexicon would allow name-valued facts.
6. **Day-precision dates**: some launch dates are month-only ("November 2025"); the compare rule needs day precision.
7. **Yes/no facts with negation**: 22 boolean change candidates are not generated; only 6 boolean facts exist.

## 7. Statement on padding
I did not pad. `run_main` has 411 claims, 589 short of 1,000, and I did not add relaxed, combinatorial or mismatched claims to it. The runs that reach 956 or 1,000 (`run_samekind_strict`, `run_max_relaxed_samekind_top1000`) exist as measurements of what relaxing would take; `NOT_SAFE*.md` marks them in their audit folders, and they should not be submitted.
Possible safe addition not done: the 424 date-only cross-attribute compares (about 835 in total) are true and contract-valid but combinatorial and unreviewed by the referee [unverified]; adding them is a decision for the coordinator.

## 8. Files
* Runs (never overwritten): `output/run_main`, `run_highprecision`, `run_relaxed`, `run_samekind_strict`, `run_max_relaxed_samekind_top1000`, `run_synthetic_extra`, and new `run_extra_openie`, `run_extra_slotfill`, `run_extra_both`, `run_extra_both_anyrule_diagnostic`.
* Audit: `output/audit_run_main/` (`review_notes.md`, `audit_independent.json`, `recheck_output.json`, `validate_claims_report.json`, `extra_fact_precision_vs_gold.json`), `audit_run_relaxed/`, `audit_run_samekind_strict/`, `audit_run_max_relaxed_samekind_top1000/`, `audit_run_highprecision/`.
* Scripts added: `audit_sample.py`, `audit_independent.py`, `recheck_output.py`, `extra_precision.py`; edited: `extra_facts.py` and `generate_claims.py` (one added choice, `agree_or_form`). Nothing outside `experiments/claim_factory/` was changed.
* Reproduce: `py experiments/claim_factory/generate_claims.py --out experiments/claim_factory/output/run_new` then `validate_claims.py --claims .../claims_valid.csv`.
