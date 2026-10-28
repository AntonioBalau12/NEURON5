# Deployment notes

Measured on the author's laptop (Intel i7-8550U, 4 cores / 8 logical, Windows, Python 3.14), child process pinned to 2 logical CPUs
with a Windows affinity mask. **Indicative only**: not the target container, not Linux. Estimates are marked **estimate**.

## Offline and dependencies

* Python standard library only (imports across the module: `argparse, calendar, csv, hashlib, json, math, random, re, sys, time, pathlib, dataclasses, collections`).
  No `pip install`, no numpy, no model download, no network call anywhere in the extraction path (grep of imports; no `socket`, `urllib`, `requests`).
* Runtime files: `extract_slots.py`, `engine.py`, `pipeline.py`, `values.py`, `linking.py`, `model.py` (96,163 bytes together), `model/*`
  (158,221 bytes: cue profile, logistic weights, gazetteer, count units, thresholds), `data/lexicon.json` (21,206 bytes). About 0.27 MB in total.
  `foundation.py`, `eval_dev.py`, `selfcheck_dev.py` and the dev CSV are not needed at run time. The dev CSV is only read when re-fitting (`model.py`).
* No random numbers are used in extraction (code reading). Run-to-run identity of output was not tested.
* Command:
  `python experiments/slot_filling/extract_slots.py --input <csv with id,text,date[,label]> --lexicon data/lexicon.json --out <facts.jsonl>`.
  It also writes a mapped CSV beside the output (or the path given with `--csv`).

## Resource measurements (current code, `bench.py`)

| Input | rows | extract s | rows/s | wall s | peak RSS |
|---|---|---|---|---|---|
| `full_input.csv` | 1897 | 3.92 | 484.5 | 4.36 | 22.3 MB |
| `full_input.csv` repeated to 20,000 rows (ids suffixed) | 20000 | 38.43 | 520.4 | 38.98 | 52.5 MB |

Output size for the 20,000-row run: 15,980 facts, 12.75 MB JSONL, 3.97 MB mapped CSV.
Interpreter start and load (lexicon + model) took 0.05 to 0.11 s.

The extractor is a single Python process with no threads or multiprocessing in the code, so the second CPU is expected to stay idle (CPU utilisation was not measured). The peak RSS includes every fact kept in a Python list
for the CSV writer; the 20,000-row figure is 2.4 times the 1,897-row figure, so memory grows with the number of facts and is not constant.

## Fit against the limits

Limits quoted by the task: 2 CPUs, 6 GiB, 3 GiB, 30 minutes, about 20,000 rows. I read 6 GiB as memory and 3 GiB as the image or disk budget; this reading is an assumption.

| Limit | Measured | Margin |
|---|---|---|
| 2 CPUs | Runs on 1 (extra CPU idle). Sharding the input in two processes would use both; not measured. | fits |
| 6 GiB memory | 52.5 MB peak at 20,000 rows | about 1% of the limit (arithmetic on the measured value) |
| 30 minutes | 38.98 s wall at 20,000 rows | 46 times under (1800 / 38.98) |
| 3 GiB | Code and model about 0.27 MB; output about 16.7 MB (JSONL + CSV) | well under; see image size below |

Caveats on the 20,000-row figure:

* The input is the 1,897 real rows repeated about 10.5 times. Real new text could be slower or faster. If it were 10 times slower than measured
  (**estimate**, not measured) the run would take about 6.5 minutes, still within 30 minutes.
* The target CPU is probably slower or faster than this laptop; the measurement was done with the current code, not the code that produced the frozen file
  (the frozen file came from an earlier state, see `REPORT.md`). The pipeline structure is the same, so speed should be similar (**estimate**).
* Throughput varies with row length and with how many entities and numbers a sentence has.

## Docker image size

Docker Desktop's daemon was not running in this environment, so **no image was built and no size was measured**.
**Estimate** from general knowledge, not measured here: a `python:3.12-slim` base is on the order of 120 to 150 MB uncompressed. The code, model and lexicon add about 0.3 MB.
The image would therefore be roughly 150 MB, far under 3 GiB. Python 3.14 is what was used to produce the numbers above; other Python versions were not tested.

Untested Dockerfile sketch:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY data/lexicon.json data/lexicon.json
COPY experiments/slot_filling/*.py experiments/slot_filling/
COPY experiments/slot_filling/model experiments/slot_filling/model
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "experiments/slot_filling/extract_slots.py", "--lexicon", "data/lexicon.json"]
```

(This copies the debugging scripts too; copy only the six runtime modules to keep the image minimal.)

## Things to know before deploying

* The model (`model/`) was fitted on the dev rows. Updating it means re-running `py experiments/slot_filling/model.py` on dev rows only.
* The frozen output must not be regenerated with the current working tree: it gives 1531 facts instead of 1595 (see `REPORT.md`).
* All facts come out as `verification_status = candidate`; the `negated` flag on non-boolean facts is unreliable (see `FAILURES.md`).
