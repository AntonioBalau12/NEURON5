# Evaluation harness for fact reconstruction

Evaluator-side code. Extractors never import it and never read `experiments/shared/_heldout`.

## Files

| file | purpose |
|---|---|
| `common.py` | paths, value equivalence (`value_key`, `fact_key`), facts-file loader, lexicon mention finder |
| `build_eval_set.py` | builds the 135-row stratified set and the worksheet (already run; do not rerun after extractor outputs exist) |
| `baseline_parser.py` | leak-free wrapper of `core/graph/parsing.py` (priors from dev rows only) |
| `combine.py` | `union`, `union_resolved`, `intersection` of OpenIE and slot filling |
| `metrics.py`, `reporting.py` | metric code and report writer (library) |
| `evaluate.py` | CLI: score methods, write a new results folder |
| `measure_resources.py`, `resource_commands.json` | CPU, wall time, peak RAM per method |
| `ingest_worksheet.py` | recompute metrics from a human-verified worksheet |
| `annotated_examples.md` (`make_annotated_examples.py`) | 32 annotated sentences |
| `REPORT_TEMPLATE.md` | report skeleton |
| `tests/` | `py -m pytest experiments/evaluation/tests -q` |
| `eval_set/`, `worksheet/`, `review/`, `output/`, `results/` | data, worksheet, judgements, baseline and combined facts, results |

## Run the full comparison (after OpenIE and slot filling have written `facts.jsonl`)

```
$env:PYTHONUTF8='1'
py experiments/evaluation/combine.py
py experiments/evaluation/measure_resources.py --out experiments/evaluation/results/resources_<run>.json
py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_<run>.json --out experiments/evaluation/results/<run>
```

`measure_resources.py` needs a command for `openie` and `slot_filling` in `resource_commands.json` (or `--cmd name="..."`), using `{python} {input} {out}`. Results folders are never overwritten.

## Metric definitions

* **Mapped fact.** `parse_status != unmapped` with subject, attribute and value set. Only mapped facts count in precision and recall. Duplicates of the same fact in a row count once.
* **Value equivalence.** `foundation._canonical_value_key` through `common.value_key`: quantities of one physical dimension convert (1 GB = 1000 MB), durations in fixed units convert (14 days = 2 weeks, 24 h = 1 day), months and years convert only among themselves (30 days is not 1 month), money keeps currency and billing period, dates and versions are compared as written, names are compared through the lexicon (alias = canonical name). `op` is part of the value (`over 40,000` is not `40,000`); `eq` counts as no op; counted-noun units are singularised and lower-cased. Subjects resolve through the lexicon.
* **form_gold** and **evaluator_suggested** (= form + suggested extras) are scored separately. Form is not exhaustive, so form precision and recall are lower bounds.
* **Beyond the form.** Predicted facts not in the form: *unverified candidates*, split into matching an evaluator suggestion and not. `x_conflicts_with_form_slot` = same subject and attribute as a form fact with a different value. `known or likely incorrect` = judged incorrect, or conflicting and not judged correct.
* **Exact canonical triple accuracy** = share of form facts reproduced exactly = recall vs form. Row-level variants: all gold facts found; fact set equals gold set.
* **Entity recognition** = the gold subject appears on any extracted record of that row. Reported overall, for subjects written in the sentence, and for subjects that are context-only.
* **Attribute accuracy given entity** and **value accuracy given entity and attribute** are conditional chains (a slot counts as found if any extracted fact has that subject and attribute).
* **Negation**: boolean-false gold facts must have `negated=true`. Recall on them, specificity on matched non-negated facts, flag accuracy on matched facts, and exact accuracy in rows containing negation words.
* **Temporal**: cue words per row (regex plus evaluator override). Cue capture = some fact of the row has a `temporal_qualifier` overlapping a cue. Non-fabrication = no qualifier on cue-free rows; every date set in `fact_observation_date`/`valid_*` must be written in the text, and a date equal to the page date that is not in the text is counted as copied.
* **Confidence intervals**: cluster bootstrap over evaluation rows, 2000 resamples, seed `20261028`, 95% percentile interval. Paired differences use the same resamples for both methods.

## Worksheet for human verification

Copy `worksheet/annotation_worksheet.csv` (or the `.md` for reading), fill:

| column | content |
|---|---|
| `reviewed` | `yes` for rows you checked (others are ignored) |
| `annotator` | your name |
| `form_fact_verdicts` | `F1=ok; F2=wrong` (unmentioned form facts are kept) |
| `suggested_fact_verdicts` | `S1=ok; S2=reject` (unmentioned suggestions are dropped) |
| `human_extra_facts` | `subject \| attribute \| value`; separate facts with `;` or a new line |
| `human_complete_facts` | the complete list; it replaces everything else. `NONE` = no usable fact |
| `human_notes` | free text |

Value shorthand: `3200 seat`, `€59/month`, `99.9%`, `v2.3`, `2026-03-12`, `true`, `>40000 user`, `128 GB`, `14 days`, a name. Then:
`py experiments/evaluation/ingest_worksheet.py --worksheet <filled.csv> --out experiments/evaluation/results/<run>_human`.
On reviewed rows the human list is treated as complete, so precision there is a real precision.

## Judging facts beyond the form

`evaluate.py` writes `judgement_template_unreviewed_candidates.csv`. Fill `verdict` (`correct`, `incorrect`, `unclear`) and `reviewer`, append the rows to `review/evaluator_judgements.csv` (columns `source_row_id, subject, attribute, value, verdict, reviewer, note`; `value` is JSON or shorthand). Judgements apply to every method that extracted the same fact. The file currently holds the evaluator's (`evaluator_llm`) verdicts for the 8 baseline candidates; they are not human-verified.

## Known limits

* 53 of 183 form facts have a subject that is not written in the sentence; sentence-only methods cannot recover them.
* No sentence of the set states an explicit observation date; validity intervals are not scored.
* The `likely_incomplete_form` stratum comes from a text heuristic and over-flags; by reading, the form misses a fact in about 4 rows.
* Memory for process trees is sampled every 20 ms; CPU comes from the Windows job object.
* A repository-root `evaluate.py` exists, so the library part of this CLI is named `reporting.py`.
