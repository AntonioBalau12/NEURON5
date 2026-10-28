# Deployment notes (OpenIE-style extractor)

"Measured" means I ran it in this worktree (Windows 10/11, Python 3.14.0, Intel i7-8550U laptop with 7.9 GiB RAM, not a 2-CPU container). "Estimate" means I did not measure it.

## Runtime requirements

| Question | Answer |
|---|---|
| Works offline? | Yes. No network call, no model download, no external service at extraction time. It reads three local files: the input CSV, `data/lexicon.json` (21,206 bytes), and `experiments/openie/data/relation_table.json` (147,175 bytes). |
| Third-party dependencies | None. Imports are `argparse, calendar, csv, ctypes, dataclasses, json, math, os, re, resource, sys, time, pathlib, collections` (standard library). `ctypes` is used only for the Windows peak-memory report; `resource` only on Linux. |
| Python 3.14 compatibility | Measured: the extractor, `eval_dev.py` and `tools/test_values.py` (99/99 checks) run on Python 3.14.0. Nothing else is needed, so there is no wheel-availability risk. The Linux branch of `peak_rss_mb()` (`resource.getrusage`) was not run here. |
| Deterministic? | Yes. Re-extracting all dev rows in memory with the saved table reproduced the frozen facts exactly (`eval_dev.py` prints `True`). No random numbers, no threads. |
| LLM / generative model at run time | None. |
| Input contract | CSV with `id`, `text`, `date`, and optionally `label`. A `form` column is ignored. |
| Command | `py experiments/openie/extract_openie.py --input <rows.csv> --lexicon data/lexicon.json --out <facts.jsonl>` (also writes `facts_mapped.csv` next to `--out`). |

## Image size impact

Measured payload: `oie/*.py` + `extract_openie.py` = 82,495 bytes, relation table 147,175 bytes, lexicon 21,206 bytes, so about 0.25 MB in total. The image grows by that amount on top of a Python interpreter that the image needs anyway. Estimate: a slim Python base image is on the order of 100 to 150 MB; I did not build an image.

Alternatives I did not adopt (sizes not measured here):
- spaCy: the install log shows 45 packages for `spacy` alone on 3.14, and a language model would be an additional download. No model was installed.
- Stanford CoreNLP OpenIE: needs a JVM (only Java 8 is installed here) plus model jars. Not tried.

## Fit to 2 CPUs / 6 GiB / 3 GiB image / 30 min for about 20,000 rows

| Resource | Measured | Estimate for the target container |
|---|---|---|
| Time | 20,867 rows (11 copies of `full_input.csv`, fresh ids): 33.3 s extraction, 34.0 s wall, 626.6 rows/s, single process. Real 1,897-row runs on the same machine gave 248 to 653 rows/s depending on load. | Even at one tenth of the slowest observed speed (about 25 rows/s) 20,000 rows take about 13 minutes, inside 30 minutes. Single-threaded, so the second CPU is unused. *(estimate)* |
| Peak memory | 67.1 MiB working set at 20,867 rows (25.7 MiB at 1,897 rows). Growth is roughly 2 KiB per row, because the script keeps all facts in memory to write the CSV view. | Far below 6 GiB. *(estimate by extrapolation: about 65 MiB at 20,000 rows, which matches the measurement)* |
| Disk | Output for 20,867 rows is written to `output/_scale/` and deleted; the real 1,897-row `facts.jsonl` is 1.67 MB, so about 18 MB for 20,000 rows. *(estimate by scaling)* | Negligible. |
| Image | About 0.25 MB of payload (above). | Well inside 3 GiB; the base image dominates. |

The scale test repeats the same 1,897 texts, so it measures per-row cost and memory, not variety. The extractor has no cache, so repetition should not flatter the speed, but I did not test that explicitly.

## Operational caveats

- Run it from the repository root or pass absolute paths; `--lexicon` and `--table` default to local files only for the table.
- `extract_openie.py` writes `facts_mapped.csv` next to the `--out` file. Point `--out` at a scratch directory when testing so that the frozen `output/facts_mapped.csv` is not overwritten (`tools/scale_test.py` now does this).
- The relation table was learned on dev rows. If the lexicon gains attributes that were never seen in dev, those attributes are matched only by their words, and the fact is marked `partial`.
- Accuracy depends on the vocabulary of the dev rows; see `REPORT.md` section 2 for the dev cross-validation numbers (these are not held-out results).
