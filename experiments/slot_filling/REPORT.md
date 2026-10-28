# Slot filling: report

Subagent B, offline schema-guided slot filling. All numbers below were measured by scripts in this folder unless marked
**estimate**. Dev numbers are the author's own self-check, not the independent evaluation.

## 1. What was built

Frozen output: `output/facts.jsonl` (1595 facts over 1897 input rows, sha1 `a60e086b140b3befb9382f50c2711d375e9ead67`,
`fact_schema.py`: 1595 valid, 0 invalid). Pure Python standard library, no generative model, no network.

Pipeline (files in this folder):

| Step | File | What it does |
|---|---|---|
| Subject linking | `linking.py` | Regex longest-match of every lexicon spelling (name + aliases) from `data/lexicon.json`; sentence splitting per `value-forms.md`. |
| Value mentions | `values.py` | Regex readers for typed values: numbers (digits, `1,234`, decimal comma, number words, `k`/`M`/thousand/million/bn), money (symbols, ISO codes, words, `per` period), percent, durations, physical units, counted nouns (a number plus up to two words; all readings are kept), dates (ISO, `12 March 2026`, `March 12, 2026`, `March 2026`, bare year), versions, names. 91 READ and 38 NOT_READ unit checks typed from `value-forms.md` pass (`py experiments/slot_filling/test_value_forms.py`: failures 0). |
| Names | `engine.py` | A name value is a lexicon entity, a name in the dev-learned gazetteer (34 names), or an unknown capitalised phrase (needs a higher threshold). |
| Candidates | `pipeline.py` | For each value mention and each entity in the same sentence, one candidate per lexicon attribute of that entity whose dev profile has seen that value kind and sub-form (unit class, billing period, date precision, name type). Attributes never seen in dev ("cold") are tried only if an attribute-name token occurs in the sentence. Booleans are one pseudo mention per entity clause. |
| Scoring | `engine.py` | Per-attribute cue profile (stems of words near/far from the value, op, kind, sub-form counts) from dev gold. A 50-weight softmax (`GroupLogit`) scores the candidates of one mention plus a "none" option. Features include cue overlap, attribute-name overlap, token distance, entity rank, pronoun. |
| Selection | `pipeline.py` | Best candidate per mention, per-kind threshold (`model/thresholds.json`), one value per (subject, attribute, form) per sentence. If the runner-up is within 0.3 the fact is `ambiguous`. |
| Facts | `extract_slots.py` | Builds the exchange format. Every fact has `verification_status = candidate`. |

### Learned tables and how they were derived (leakage statement)

* The learned files are in `model/`: `cue_profile.json` (+ readable `cue_table.tsv`, 312 attributes with at least one example), `lr_weights.json`
  (50 weights), `name_gazetteer.json` (34 names), `count_units.json` (83 units), `thresholds.json`.
* `model.py` fits them from the gold `form` column of `experiments/shared/data/dev_rows.csv` only (1627 rows, 2070 gold facts).
  A gold fact becomes a cue example only when its value is found in the sentence by the regex readers. `data/practice.csv` and
  `experiments/shared/_heldout/` were not opened.
* **The model in `model/` is fitted on all 1627 dev rows.** Scoring the frozen output on dev rows is therefore in-sample and
  optimistic. The frozen output for the 270 non-dev rows did not see their forms.
* `output/cv_facts.json` **is out-of-fold**: `eval_dev.py` assigns each dev row to 1 of 5 folds by md5 of the row id, refits the
  profile, gazetteer, count units and weights on the other four folds, and extracts the held-out fold. Even so, CV is still
  optimistic: (a) the code, regexes and rules were written while reading dev rows and their failures; (b) per-kind thresholds in
  `thresholds.json` were chosen from a CV sweep over the same dev rows (`eval_dev.py --tune`).
* The `unknown` and `gazetteer` name paths use the gazetteer built from the training folds only in CV.

### Provenance caveat found while finishing (not fixed, by instruction)

The files were modified in this order (file mtimes): `facts.jsonl` 20:12:34, `model/*` refit 20:14:59, `thresholds.json` 20:18:14,
`values.py`/`engine.py`/`pipeline.py`/`eval_dev.py` 20:20:49 to 20:21:24, `cv_facts.json` 20:22:41. So:

* The frozen `facts.jsonl` was produced by an earlier code/model state than the one in this folder. Re-running the current
  code on `full_input.csv` (written to a scratch path, since deleted) gives 1531 facts instead of 1595. By unique
  (row, subject, attribute, value): frozen 1590, current 1526, in both 1500, frozen only 90 (money 40, name 20, date 14, quantity 13, others 3),
  current only 26. The current code is **not** a reproduction of the frozen file.
* `cv_facts.json` was produced by the current code, so the out-of-fold numbers describe the current code, not exactly the frozen
  file. For the frozen file the only dev number that describes it directly is the in-sample one (section 2).
* The earlier `dev_summary.json`, `dev_cv_facts_annotated.jsonl`, `dev_extras_all.jsonl`, `extras_sample.jsonl` were made from an
  older CV run and no longer match `cv_facts.json`. They were moved to `output/stale_pre_final/` and are not used.

## 2. Dev self-check (`selfcheck_dev.py`, output `selfcheck_dev.json`)

Match rule: same subject (case-folded), same attribute, same value kind, and either identical value objects or
`foundation.compare_values(gold, pred, "eq") is True` (so `1 GB` equals `1000 MB`, names compare after removing spaces/hyphens).
Values carrying `op` match only an identical object. Predictions are de-duplicated on (subject, attribute, value).
"Wrong value" = the form has this subject+attribute with a different value. "Extra" = subject+attribute are not in the form at all.
The form lists only the facts a claim needs, so an extra is not automatically an error (see section 3).

| Setting | gold | predicted | correct | wrong value | extra | precision | recall |
|---|---|---|---|---|---|---|---|
| CV, out-of-fold (current code, thresholds applied) | 2070 | 1239 | 1193 | 4 | 42 | 0.963 | 0.576 |
| Frozen `facts.jsonl` on dev rows, **in-sample (optimistic)** | 2070 | 1386 | 1334 | 16 | 36 | 0.962 | 0.644 |

Only 1419 of the 2070 gold facts have their gold subject named in the sentence (the rest use an event or
parent entity such as `Hooly Q4 2025 Results`, or a speaker context). Recall among those reachable facts: CV 0.841, frozen in-sample 0.940.
At most 0.686 recall is reachable for a linker that only uses subjects named in the text.

Per value kind, CV out-of-fold (frozen in-sample in `output/kind_table.csv` and `attribute_coverage_summary.md`):

| kind | gold | named in text | predicted | correct | wrong value | extra | precision | recall |
|---|---|---|---|---|---|---|---|---|
| quantity | 885 | 614 | 607 | 591 | 2 | 14 | 0.974 | 0.668 |
| money | 224 | 157 | 118 | 114 | 0 | 4 | 0.966 | 0.509 |
| percent | 177 | 84 | 81 | 81 | 0 | 0 | 1.000 | 0.458 |
| duration | 199 | 125 | 113 | 111 | 1 | 1 | 0.982 | 0.558 |
| date | 144 | 107 | 71 | 68 | 0 | 3 | 0.958 | 0.472 |
| version | 110 | 108 | 108 | 104 | 0 | 4 | 0.963 | 0.945 |
| name | 183 | 104 | 56 | 47 | 1 | 8 | 0.839 | 0.257 |
| boolean | 148 | 120 | 85 | 77 | 0 | 8 | 0.906 | 0.520 |

Frozen in-sample per kind (precision / recall): quantity 0.979/0.671, money 0.974/0.679, percent 1.000/0.475, duration 0.992/0.613,
date 0.937/0.618, version 0.981/0.964, name 0.811/0.421, boolean 0.932/0.743.

Precision by `parse_status` (CV): complete 0.972 (1131/1164), ambiguous 0.880 (22/25), partial 0.800 (40/50).
Frozen in-sample: complete 0.972 (1308/1345), ambiguous 0.667 (14/21), partial 0.600 (12/20).

### Extras review (own observation; `output/extras_review.csv`)

The out-of-fold run has 46 predictions that are not in the form (42 extra + 4 wrong-value). The planned fixed-seed sample
(seed 20261029, size up to 60) is larger than the population, so **all 46 were reviewed** against the sentence by the author:
**15 correct, 5 uncertain, 26 incorrect.** Counting the 15 correct extras as true, the out-of-fold precision is about
(1193+15)/1239 = 0.975 (an upper reading; the uncertain ones are left out of the numerator). The 26 incorrect ones are
dominated by attribute confusion between near neighbours (max vs included seats, price vs extra-seat price, context window vs output length),
wrong subject (speaker label as subject, sibling product), and a counted noun taken from a verb.

## 3. Attribute coverage (`output/attribute_coverage.csv`, `attribute_coverage_summary.md`)

321 lexicon attributes. CV status: ok 221, **zero extraction 86**, extracted but none correct 11, no dev gold 3
(`ai_editing`, `livestreamed`, `newsletter_subscribers`). Among the 318 attributes with dev gold, CV recall is 0 for 97,
under 0.5 for 49, 0.5 to 0.9 for 99, and at least 0.9 for 73. 54 attributes have no fact at all in the frozen output over all
1897 rows. Zero extraction is mostly structural: the attribute is only ever recorded under an entity that is not named in the
sentence (`headcount`, `guidance`, `rent`, `speakers`, `venue`) or is a yes/no with no cue (`copilot_included`, `offline_maps`).

## 4. How specific phenomena are handled

* **Negation.** Boolean facts: a negation word in the entity's clause (`not, no, never, none, nobody, nothing, neither, nor, without, cannot, n't`;
  `no more than`-style comparisons excluded) gives `value: false`, `negated: true`. Frozen output: 55 false booleans, all with `negated: true`.
  A numeric/typed mention preceded by a negation in its clause is suppressed (not emitted). For other kinds `negated` is set from any
  negation word in the clause (clauses end at `. , ; : ! ?`). The frozen file has 6 such non-boolean facts (5 quantity, 1 money); in all 6 the
  word is not a negation of the value (`never misses a beat`, `at no charge`, `cost nothing`, `is not affected`, `AI answers are not part of it`).
  Treat `negated` on non-boolean facts as unreliable (see FAILURES.md).
* **Approximation.** A value after `about, around, approximately, roughly, nearly, almost, circa, ~, ≈, ±` or before `or so, -ish` is suppressed and
  never emitted as an exact value (`APPROX_BEFORE/AFTER` in `values.py`; `about 5 GB` is flagged approximate in a direct check).
* **Ranges.** `10-20 GB`, `10 to 20 GB`, `between 10 and 20`, `1 or 2 days`: both ends are suppressed.
* **Bounds.** `up to / at most / no more than` = `le`, `at least / no less than / minimum` = `ge`, `over / more than / above` = `gt`,
  `under / less than / below` = `lt`, plus `or more / or less / +`. For durations `within` = `le`. Dates: `by / no later than` = `le`,
  `before` = `lt`, `after` = `gt`. Frozen output has 27 facts with `op` (le 18, gt 5, lt 3, ge 1).
* **Numerics.** Thousands separators, decimal comma (`5,50 euros` = 5.5), number words
  (`seven`, `twenty-one`), `2 million users` = 2000000. Runs like `1.234` (three decimals) and dotted runs are ambiguous and give no value. Scales (`k`, `M` case sensitive since `m` is metre, thousand, million, bn), and `€`, `$`, `£`, ISO codes, `euros`.
  Values are normalised to the contract (EUR 18 million = 18000000). Invisible characters (zero-width, soft hyphen) next to a value make it unreadable.
* **Dates.** Only fully valid calendar dates are accepted (a month 13 is rejected). Precision is kept (`2026`, `2026-03`, `2026-03-24`).
* **Page date vs event date vs validity.** `source_publication_date` is copied from the row `date` only (checked: equal to the input for all 1595 facts).
  It is never used as a value or as `fact_observation_date`. All 105 date facts have their surface string in the sentence (12 of them happen to equal the page date,
  and in all 12 the date is written in the text). `fact_observation_date` is set only for `as of <full date>` (0 facts in the frozen file);
  `valid_to` only for `until/till/through <full date>` (0 facts); `valid_from` only for `since/from <full date>` on a non-date value (10 facts, e.g. p-27 price from 2026-06-02).
  Partial dates after these words are not copied into the fields but noted in `notes`. `temporal_qualifier` is the raw word (177 facts: now 57, today 45, since 16, still 15, yet 11, from today 9, already 9).
* **Source label.** Copied to `source_label` only (1319 true, 251 false, 25 unsure facts). It does not influence extraction.

## 5. Frozen output: distribution

1595 facts in 1222 of 1897 rows (1059 dev rows, 163 non-dev rows; 204 facts from the 270 non-dev rows). By kind: quantity 693, money 187,
version 126, boolean 136, name 107, date 105, percent 97, duration 144. 267 distinct attributes.
`parse_status`: complete 1539, ambiguous 29, partial 27, unmapped 0. Mean confidence 0.931; 41 facts have confidence below 0.6.
Span check: `text[span_start:span_end] == source_text_span` for all facts.

## 6. Speed and memory (indicative)

`bench.py` runs `extract_slots.py` as a child process pinned to 2 logical CPUs on an Intel i7-8550U laptop (Windows, Python 3.14).
The extractor is single-threaded Python, so the second CPU is idle. Measured with the **current** code (not the frozen code):

| Input | rows | load s | extract s | rows/s | wall s | peak RSS |
|---|---|---|---|---|---|---|
| `full_input.csv` | 1897 | 0.05 | 3.92 | 484.5 | 4.36 | 22.3 MB |
| `full_input.csv` repeated to 20,000 rows | 20000 | 0.11 | 38.43 | 520.4 | 38.98 | 52.5 MB |

The 20,000-row input is the 1897 real rows repeated (ids suffixed); it is a stand-in, not new text. See `DEPLOYMENT.md`.

## 7. Files

`REPORT.md`, `FAILURES.md`, `DEPLOYMENT.md`; `selfcheck_dev.py`, `build_extras_review.py`, `bench.py`; `output/selfcheck_dev.json`, `kind_table.csv`,
`attribute_coverage.csv`, `attribute_coverage_summary.md`, `extras_review.csv` (+ `extras_review_input.jsonl`), `failure_candidates.jsonl`,
`_bench/bench.json`. Extractor, model and frozen output were not modified in this pass. `_dbg.py`, `_fn.py`, `_row.py` are debugging scratch scripts from earlier work.
