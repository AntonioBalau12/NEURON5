# Fact reconstruction: evaluation report  (TEMPLATE)

Fill every `<...>` from `results/<run>/summary.md` and `metrics.json`. Delete the instruction lines (in *italics*). Do not write a number that is not in a results folder, and name the folder.

- Results folder: `experiments/evaluation/results/<run>`  (config.json inside metrics.json has file hashes)
- Date: `<date>`   Evaluator: `<name>`   Worksheet status: `<none | n rows human-verified, file, annotator>`
- Commit of the code: `<git rev-parse HEAD>`; facts files used: `<paths and sha1 from metrics.json>`

## 1. Question and verdict

*Two or three sentences. Which method (or combination) should be used to rebuild atomic facts from text, and what is the evidence.* 

Verdict: `<method>` because `<one number with its interval and what it is measured against>`. Confidence: `<low | medium | high>` because `<set size, form incompleteness, human verification>`.

## 2. What was evaluated

| item | value |
|---|---|
| evaluation rows | `<135>` (`<120>` held-out, `<15>` dev control), chosen before any extractor output (`eval_set/selection_provenance_addendum.json`) |
| gold | form facts `<183>` (dataset form, incomplete), evaluator suggestions `<4>` (unverified), human-verified rows `<n>` |
| input to every method | `id, text, date, label` only |
| value equivalence | `foundation._canonical_value_key` (units convert, names via lexicon), plus op kept, `eq` = no op, counted nouns singularised |
| strata | `<table: stratum, rows in set, rows in pool>` from `eval_set/selection_log.json` |

## 3. Headline results

*Paste table 1 of summary.md (precision/recall/F1 against form and against suggested; intervals in brackets). Keep the 95% intervals.*

| method | precision vs form | recall vs form | F1 vs form | recall vs suggested | CPU s | peak RAM MB |
|---|---|---|---|---|---|---|
| deterministic baseline | | | | | | |
| OpenIE | | | | | | |
| slot filling | | | | | | |
| combined: union | | | | | | |
| combined: union_resolved | | | | | | |
| combined: intersection | | | | | | |

Reading rules to repeat in the text:
1. The form is not exhaustive. *Recall vs form* is a **lower bound** on recall of what the sentences state. *Precision vs form* is a **lower bound** on precision, because a correct fact beyond the form counts as an error.
2. `<n>` of the `<n>` rows have a subject that is not written in the sentence. A sentence-only method cannot reach 100% recall; the ceiling is about `<1 - 53/183 = 71%>` of the form facts.
3. Differences inside each other's 95% intervals are not differences (paired differences are in section 8 of summary.md).

## 4. Facts beyond the form (unverified candidates)

| method | beyond form | matching an evaluator suggestion | not suggested | reviewed | judged correct | judged incorrect | automatic conflicts with a form slot | still unreviewed |
|---|---|---|---|---|---|---|---|---|

*Say exactly how many were reviewed and by whom (`review/evaluator_judgements.csv`, reviewer column). State the precision range: lower bound = precision vs form, approximate upper bound = every unreviewed extra right. If the range is wide, say the true precision is not determined.*

*Do not write "recovered `<n>` new facts" unless they are judged correct. Otherwise write "`<n>` unverified candidates, of which `<k>` match an evaluator suggestion".*

## 5. Where it fails (component accuracy)

*Table 3 of summary.md.* Entity recognition (written / implicit subject), attribute given entity, value given entity and attribute. Add two sentences on the weakest step per method.

Top error types per method: *count the `reason` column of `per_method/<m>/missed_gold_facts.csv` (`entity_not_found`, `attribute_not_found`, `slot_found_but_value_missing`, `wrong_value`) and give three example ids each.*

## 6. Value kinds and strata

*Table 5 (per kind) and table 6 (per stratum).* Name the two best and worst strata per method. A stratum with fewer than 20 form facts gets the words "very few facts".

## 7. Negation and time

| method | negation recall | negation specificity | temporal cue captured | no qualifier on cue-free rows | dates set that the text does not support |
|---|---|---|---|---|---|

*Limits to state: the set has `<14>` boolean-false facts and `<28>` rows with a temporal cue; no sentence states an explicit observation date, so validity intervals and "date copied from the page" are checked only as "none were fabricated". See `per_method/<m>/temporal_cases.csv`.*

## 8. Combination

| variant | rule | precision vs form | recall vs form | facts both agree on | conflicting slots |
|---|---|---|---|---|---|
| union | all distinct facts, conflicts kept and flagged ambiguous | | | | |
| union_resolved | one fact per conflicted slot (agreement, status, confidence, slot_filling) | | | | |
| intersection | only facts both methods extracted | | | | |

*Counts of agreement come from `output/combined_<variant>_facts.jsonl.run_info.json`. The variants were fixed before real outputs were compared; say if any rule was changed afterwards and why.*

## 9. Resources

*From `resources.json` (sequential subprocesses, 2 threads, same input of `<1897>` rows).* CPU seconds, wall seconds, peak working set, CPU per 1,000 rows, `cpu_per_wall` (above 2 means the thread cap leaked). The combined pipeline cost is openie + slot_filling + combine.

## 10. Limitations (keep all that apply)

- Small, purposive set (`<135>` rows), not a random sample. Intervals cover row sampling only.
- Form facts are the dataset's own; `<12>` rows carry a concern that a form fact is not stated by the sentence.
- Evaluator suggestions are made by a model reading the sentence. They are not verified unless a human marked them.
- `<n>` of the beyond-form facts are unreviewed; precision is a range, not a point.
- Dev rows were used to tune the methods; the `<15>` dev rows are a control, not a test.
- Temporal and negation gold is thin (see section 7).
- One machine, one run unless `repeats > 1`; memory for process trees is sampled.

## 11. Reproduce

```
py experiments/evaluation/build_eval_set.py             # only to regenerate the set; do not rerun after outputs exist
py experiments/evaluation/baseline_parser.py
py experiments/evaluation/combine.py
py experiments/evaluation/measure_resources.py --out experiments/evaluation/results/resources_<run>.json
py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_<run>.json --out experiments/evaluation/results/<run>
py experiments/evaluation/ingest_worksheet.py --worksheet <filled.csv> --out experiments/evaluation/results/<run>_human
py -m pytest experiments/evaluation/tests -q
```

## 12. Decision record

| decision | based on | reversible by |
|---|---|---|
| `<chosen method>` | `<table, number>` | `<what new evidence>` |
