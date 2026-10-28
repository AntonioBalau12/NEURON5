# Backend — NEURON5 offline CSV classification API

FastAPI service for the three-stage classification UI in `../frontend`.
Python 3.12+, no database, no LLM, **no local classifier**: classification is
delegated to the teammates' HTTP service.

## Run (local development)

```sh
cd backend
python -m pip install -r requirements.txt

# 1) start the teammates' classification service and point the backend at it
#    NEURON_CLASSIFIER_URLS=http://<their-host>:<port>/<path>
#    (payload shape: see docs/API_CONTRACT.md section 7)

# 2) while the real service is not available, use the local demo stand-in:
python -m app.mock_classifier        # http://127.0.0.1:8010 (demo labels only)
```

```sh
# 3) start the API
$env:NEURON_CLASSIFIER_URLS = "http://127.0.0.1:8010/classify"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The Next.js dev server on `http://localhost:3000` talks to it directly; see
`docs/API_CONTRACT.md` for CORS/cookie rules.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEURON_CLASSIFIER_URLS` | — (required) | comma-separated POST endpoints, tried in order |
| `NEURON_CLASSIFIER_MODE` | `csv` | `csv` = multipart upload, `rows` = JSON rows |
| `NEURON_CLASSIFIER_FIELD_NAME` | `file` | multipart file field name |
| `NEURON_CLASSIFIER_TIMEOUT_SECONDS` | `1800` | per-request timeout, capped by the job deadline |
| `NEURON_CLASSIFIER_RETRIES` | `0` | retries per endpoint (long requests are not retried by default) |
| `NEURON_CLASSIFIER_TOKEN` | — | optional `Authorization: Bearer` token |
| `NEURON_TEMP_DIR` | system temp | dataset snapshots, job outputs |
| `NEURON_MAX_CONCURRENT_JOBS` | `1` | one active job at a time |
| `NEURON_JOB_DEADLINE_SECONDS` | `1800` | job budget; `ARENA_DEADLINE` also caps it |
| `NEURON_RESULT_GRACE_SECONDS` | `600` | result kept downloadable after completion |

## CLI (processor without HTTP, etapa B)

Sends the CSV to the same HTTP service; no uvicorn needed:

```sh
cd backend
python -m app.engine.cli --input ../data/practice.csv --output /tmp/out.csv \
    --classifier-url http://127.0.0.1:8010/classify
```

## Tests

```sh
cd backend && python -m pytest -q
```

## Layout

```text
backend/
  app/
    config.py            settings (limits, deadlines, classifier endpoints)
    main.py              FastAPI app factory + CORS + lifespan
    api/                 sessions, datasets, jobs, events, results routers
    engine/
      api.py             Engine/MappingSpec/processor interface (frozen)
      remote_engine.py   HTTP client for the teammates' classifier (CSV or JSON)
      processor.py       snapshot -> remote request -> validated output table
      cli.py             standalone processor entry point
      foundation.py      contract-first ingestion/lexicon helpers (ported from p0)
    mock_classifier.py   local demo stand-in for the teammates' service
  tests/                 engine + API + end-to-end tests
  docs/                  API_CONTRACT.md, DECISIONS.md
```
