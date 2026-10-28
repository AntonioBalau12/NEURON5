# OpenIE-style reconstruction: report

Everything here is my own observation on **dev** rows (`experiments/shared/data/dev_rows.csv`). It is not the independent evaluation.
No held-out rows or `data/practice.csv` were opened. `output/facts.jsonl` is frozen (sha1 `6c7bd87df54d925e96bbae6476c99e37d4a55f0d`, 2,184 facts, 1,897 input rows) and was not regenerated.

Reproduce the numbers: `py experiments/openie/eval_dev.py` (writes `output/eval_dev.txt`, `eval_dev.json`, `extras_review.csv`, `misses_dev.csv`).

## 1. What was actually built

A stdlib-only, offline, rule-plus-counts pipeline. It is "OpenIE-style" (subject, relation words, object) but it is **not** a general OpenIE system: there is no syntactic parse and no neural model.

| Step | Code | What it does |
|---|---|---|
| Typed value finders | `oie/values.py` | Dates (day/month/year precision), versions, money (currency, `per`), percent, durations, quantities (physical units and counted nouns), word numbers, decimal comma. Every value keeps exact character offsets. |
| Entity mentions | `oie/entities.py`, `oie/textutil.py` | Lexicon aliases (`data/lexicon.json`), pronouns (`he/she/it/I`) resolved to the previous alias or the `Name:` speaker label, sentence splitting, stemmer. |
| Relation cue + attribute scoring | `oie/pipeline.py`, `oie/model.py` | For each value, the words on both sides (windowed, weighted by distance) are scored against every attribute of each candidate subject: lexical overlap with the attribute name plus a count table learned from dev (`data/relation_table.json`, 147 KB). Kind and unit/billing-period compatibility are checked against what the attribute took in dev. |
| Subject choice | `pipeline.subjects_for/resolve` | Only entities **named in the sentence** (or pronoun/speaker bound to one). Nearest mention in the same clause wins; rivals within a margin make the fact `ambiguous`. |
| Booleans | `pipeline.boolean_facts` | Attribute words (and learned bigrams) present for a named entity gives `true`; a negation word in the sentence gives `false` with `negated: true`. |
| Names | `pipeline.analyse` | Name values come from a dev gazetteer (34 names) or from lexicon entities used as objects. |
| Output | `extract_openie.py` | One JSONL fact per typed value, `extraction_method: openie`, `verification_status: candidate`, plus `output/facts_mapped.csv` (derived view of mapped facts). |

Relevant facts about training: `tools/learn.py` aligns dev gold forms with sentence values and stores only counts (318 attributes, 2,065 aligned gold facts, 82 counted-noun units, 34 names; `output/learn_log.txt`). The extractor never reads a `form` column at run time. **Consequence:** the table was fitted on all 1,627 dev rows, so any score of the frozen file on dev rows is resubstitution and optimistic. The 5-fold CV below (table learned on the other folds) is the honest dev estimate.

### Tried and dropped

- **spaCy.** `output`-side evidence is `spacy_install.log`: `pip install --only-binary=:all: spacy` into a local venv succeeded on Python 3.14.0 (spacy 3.8.18, thinc 8.3.14, blis 1.3.4, numpy 2.5.4, pydantic 2.14.1, `cp314-win_amd64` wheels, 45 packages in total). So wheels for 3.14 exist. The log shows **no language model** being downloaded and the `.venv` is no longer in the worktree (it is git-ignored). I did not run any spaCy parse and have no spaCy accuracy number. I dropped it to keep the Docker image free of a 45-package dependency chain and a model download that needs network access.
- **Stanford OpenIE / CoreNLP.** Not tried. `java -version` here reports Java 8 (1.8.0_503, HotSpot **Client** VM). I found no CoreNLP files on disk. I judged it unsuitable (needs a JVM and several hundred MB of models in the image; a 32-bit-style client VM limits the heap). This is a decision based on the environment, not a measurement.
- **Parameter variants** (`output/grid.txt`, `eval_dev.py --set`): `strict_partial` (single attribute word is not evidence) and `bridge_apposition` (subject of the previous clause) gave no gain in CV (recall 0.557 / 0.556 vs 0.560 for the default). `outside_margin` (mark facts ambiguous when a better attribute belongs to an unnamed entity) moved about 39 correct facts to `ambiguous` for 6 fewer errors, so it is disabled.
- **Subject inference from the lexicon** (unique owner of the hinted attribute when no entity is named). Kept as an observation only, in `notes` (`hint_attr=`, `hint_owners=`; 580 of 687 unmapped facts carry it). In 5-fold CV (`output/cv.txt`, run earlier with `tools/eval_dev.py --cv 5`) these inferred facts had precision 0.766 on their own and the combination reached P 0.924 / R 0.680. They are not in the output because the subject is not in the text.

## 2. Dev results (my own check; `output/eval_dev.txt`)

Match = lexicon-resolved subject + exact attribute + value equivalence from `foundation.compare_values(...,"eq")` (units convert; money needs the same currency and period; dates need equal precision; names via lexicon). Gold `op` is ignored in the "op-free" numbers. The extractor never emits an `op`, so "strict" counts gold facts with an `op` (35 of 2,070) as missed.

| Setting | Status filter | Predicted | TP | Extras beyond the form | Precision | Recall (op-free) | Recall (strict) |
|---|---|---|---|---|---|---|---|
| Frozen file, dev ids (resubstitution, optimistic) | complete | 1,279 | 1,257 | 22 | 0.983 | 0.607 | 0.605 |
| Frozen file, dev ids (resubstitution, optimistic) | complete + ambiguous (+partial) | 1,303 | 1,272 | 31 | 0.976 | 0.614 | 0.613 |
| 5-fold CV inside dev | complete | 1,198 | 1,160 | 38 | 0.968 | 0.560 | 0.558 |
| 5-fold CV inside dev | complete + ambiguous + partial | 1,242 | 1,192 | 50 | 0.960 | 0.576 | 0.574 |

Gold has 2,070 facts in 1,627 dev rows. The frozen file has no `partial` facts.

### Per value kind (all mapped statuses; recall over gold facts of that kind, precision over predicted facts of that kind)

| Kind | Gold | Frozen/dev recall | Frozen/dev precision | CV recall | CV precision |
|---|---|---|---|---|---|
| quantity | 885 | 0.658 | 0.990 | 0.644 | 0.979 |
| money | 224 | 0.647 | 0.973 | 0.634 | 0.973 |
| duration | 199 | 0.598 | 0.983 | 0.558 | 0.965 |
| name | 183 | 0.279 | 0.927 | 0.208 | 0.844 |
| percent | 177 | 0.429 | 1.000 | 0.418 | 0.937 |
| boolean | 148 | 0.743 | 0.957 | 0.500 | 0.937 |
| date | 144 | 0.625 | 0.957 | 0.583 | 0.923 |
| version | 110 | 0.900 | 0.943 | 0.900 | 0.943 |

Booleans lose most from resubstitution to CV (0.743 to 0.500): their detection depends on learned bigrams.

### Where recall is lost (frozen file on dev, 798 gold facts not matched, `output/misses_dev.csv`)

| Cause | Facts |
|---|---|
| Value was read but left `unmapped` (subject not named in the sentence, or attribute cue too weak) | 571 |
| Value not found at all (mostly name values, e.g. a person who is also a lexicon entity, or a city) | 135 |
| Boolean not detected | 38 |
| Value found but assigned to another subject/attribute | 23 |
| Gold carries an `op` (`le` 21, `gt` 5, `lt` 4, `ge` 1); extractor deliberately emits no comparison values | 31 |

The dominant loss is the "subject must be named in the text" rule: 597 of the 687 unmapped facts say "no entity named in the sentence" and 90 say "no attribute of a sentence subject matches the context".

### Extras (mapped facts that are not in the form)

`output/extras_review.csv`: 50 extras sampled with seed 20261029 from a pool of 51 distinct extras (the 31 extras of the frozen file on dev, plus the CV-only extras). 31 of the 31 frozen extras are in the sample (30 also arise in CV). My own labels after reading each sentence (reasons in the file):

| Origin | incorrect | correct (true but not in the form) | uncertain |
|---|---|---|---|
| In the frozen file (31) | 18 | 7 | 6 |
| CV only (19) | 18 | 0 | 1 |

So of the 31 extras in the frozen file, 18 are wrong, 7 are supported by the sentence but missing from the form (for example `p-1585` "Richard Hendrix as the CTO"), and 6 are debatable (mostly "Pixel 10 ships with Android 16.1" assigned to the OS entity instead of the phone). The wrong ones are mainly: the wrong attribute for a value in a multi-value sentence (`max_upload_size` for Free vs Pro, `included_seats` vs `maximum_seats`/`minimum_seats`), a value attached to the neighbouring subject, and a weak learned cue (`support_satisfaction` for any "% recommend/agree").

By automatic category, 19 of the 31 frozen extras (mapped statuses) have a gold value under another subject/attribute, 5 have the same subject+attribute but another value, 7 are not in the form at all.

## 3. Negation, approximation, numbers, dates

**Negation.** A negation word (`not, no, never, none, without, n't`, ...) before a value in the same clause, or anywhere in the sentence for booleans, sets `negated: true`. Comparative phrases ("no more than") are excluded. Observed on dev (frozen): 115 mapped booleans, 53 negated, and every negated one has `value: false` (none are `true`+negated). Among booleans that match gold, polarity is right in 110 of 110. Gold has 65 `false` booleans, of which 52 are recovered (0.80), and 83 `true`, of which 58 (0.70). Errors are about scope, not polarity: `p-1803` ("has not raised a Series B") also yields a `raised_series_a=false` fact, correctly flagged `ambiguous`. A non-boolean value that follows a negation in its clause is downgraded to `partial` by the code (the frozen file has no `partial` facts, so this path is not visible in the output). Booleans that need negation without a named entity are missed (`p-956`, `p-354`, `p-1767`).

**Approximation and comparison.** `about/around/roughly/nearly`, `over/under/at least/up to/more than/less than` are detected and the value is suppressed (not emitted with an exact value, no `op` invented). In dev gold, 35 facts carry an `op`; the extractor misses 31 of them by design and emits the bare number for 4 (the `op` is lost). No sentence in `full_input.csv` contains "about/around/approximately/roughly/nearly/almost" before a digit (regex check), so the approximation branch was only exercised by `tools/test_values.py` (99/99 checks pass), not by real rows.

**Numeric quality.** 584 dev facts are unmapped but carry a typed value; 572 of those (98%) equal some gold value of the row, so value reading is accurate even where mapping abstains. The 12 that do not are listed in `FAILURES.md` (for example "1.0 answers" read as a quantity, "SOC 2 Type II" read as "2 type"). Every one of the 1,272 matching mapped facts matched exactly after the foundation equivalence; I did not count how many needed a unit conversion.

**Dates.** ISO values with their written precision (`2025-06`, `2026`, `2026-05-14`). 94 mapped date facts on dev: precision 0.957, recall 0.625.

**Page date vs event date vs validity.**
- The row `date` goes only to `source_publication_date`. It is never copied into `value`, `fact_observation_date`, `valid_from` or `valid_to` (checked on the full file: `obs_date_equals_page_date: 0`; none of the dev facts has a validity or observation date equal to the page date).
- An **event date** is a `value` of kind `date` on a date attribute (`joined`, `launched`, `released`). 12 mapped date facts on dev have a value equal to the page date; they are explicit dates in the sentence ("joined Hooly on 12 January 2026"), 10 of them match gold.
- A **validity interval** is set only when a date is introduced by `as of/on` (observation), `since/from` (valid_from) or `until/till` (valid_to), attached to the non-date facts in the same clause: 1 observation date and 1 `valid_from` in the whole file. Both are debatable. `p-1178` "…Hooly Chrome 68.0 from May 26, 2026" puts a release date into `valid_from`. `p-541` "Hooly Maps 12.2 shipped on 2026-10-05" puts a ship date into `fact_observation_date`, while gold treats it as an event date (`latest_release_date`). The date itself stays unmapped in both rows.
- Relative words ("today", "now", "still", "since", "from today") are kept raw in `temporal_qualifier` (283 of 2,184 facts) and are not resolved to dates.

## 4. Fact counts (frozen file, 1,897 rows)

| | Count |
|---|---|
| Facts | 2,184 (rows with at least one fact: 1,734; rows with none: 163) |
| Mapped, `complete` | 1,467 |
| Mapped but `ambiguous` | 30 (19 rival subject/attribute, 11 several different values for one attribute) |
| `partial` | 0 |
| `unmapped` | 687 (597 no entity named, 90 no matching attribute); all carry a typed value, none has a null value |
| Mapped total | 1,497 (68.5%) |
| Dev rows | 1,887 facts: 1,279 complete, 24 ambiguous, 584 unmapped |
| Non-dev rows (270) | 297 facts: 188 complete, 6 ambiguous, 103 unmapped |

Mapped by kind: quantity 672, money 178, duration 141, boolean 126, version 122, date 108, percent 88, name 62. Unmapped by kind: quantity 338, percent 113, duration 87, money 85, date 59, version 5.

Of the 30 ambiguous facts on dev rows (24), 15 equal gold. `extraction_confidence` is an internal score (complete facts: min 0.321, median 0.69, max 0.77); I did not calibrate it. 479 mapped facts have `relation_surface: null` (no words between subject and value, no matched cue token, which includes the 126 booleans).

## 5. Throughput and memory

Measured with `tools/scale_test.py` (11 copies of `full_input.csv` with fresh ids, 20,867 rows, input columns only), single Python process, no CPU pinning, on an Intel i7-8550U laptop (4 cores / 8 threads, 7.9 GiB RAM) that was also running other work. Saved in `output/scale_test.txt`.

| Measure | Value |
|---|---|
| Rows | 20,867 (24,024 facts) |
| Extraction time | 33.3 s (626.6 rows/s) |
| Wall time including interpreter start and writing | 34.0 s |
| Peak working set | 67.1 MiB |

Earlier runs on the 1,897 real rows gave 248, 310 and 653 rows/s and 25 MiB peak (`output/timing.txt`), so the speed varies by about 2.5x with machine load; treat 626 rows/s as an upper-end indicative figure. The process is single-threaded Python (`OMP_NUM_THREADS=2` is set but nothing uses it), so the "2 threads" condition is not exercised.

## 6. Known limits

- Recall is 0.56 (CV) to 0.61 (resubstitution) because subjects that the text does not name are abstained on.
- The learned table makes the extractor dependent on the dev vocabulary. Attributes never seen in dev are only matched by exact lexical overlap with the attribute name and are marked `partial` when chosen.
- Name values (0.21 to 0.28 recall) are the weakest kind.
- `extraction_method` is `openie` on every fact, although the attribute choice uses a dev-learned table.
- Bugs I noticed and did **not** fix (the file is frozen): `source_text_span` cuts at the thousands comma ("Hooly Docs counts 2" in `p-1698`); `extract_openie.py` writes `facts_mapped.csv` next to whatever `--out` it is given, so the earlier `scale_test.py` would have overwritten the derived `output/facts_mapped.csv` (I changed `scale_test.py` to use a private `output/_scale/` directory; `facts_mapped.csv` is unchanged and matches the 1,497 mapped facts of `facts.jsonl`); the `peak_rss_mib` helper in `extract_openie.py` is only tested on Windows.
