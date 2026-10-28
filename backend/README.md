# Backend — NEURON5 offline CSV classification API

FastAPI service for the three-stage classification UI in `../frontend`.
Python 3.12+, no database, no LLM, **no local classifier**: classification is
delegated to the teammates' HTTP service.

## Run (local development)

```sh
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

That is enough for the frontend: **without `NEURON_CLASSIFIER_URLS` the API
classifies with the in-process DEMO classifier** (`app/engine/mock_engine.py`,
keyword heuristic). Jobs succeed, results/logs/downloads work, and every job log
carries the warning "DEMO classifier ... placeholders". `NEURON_MOCK_DELAY_SECONDS`
(default 1.0) keeps stage 2 visible.

When the teammates' service is ready, point the backend at it (no code change):

```sh
$env:NEURON_CLASSIFIER_URLS = "http://<their-host>:<port>/<path>"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Optional: exercise the real HTTP client path against a stand-in:

```sh
python -m app.mock_classifier        # http://127.0.0.1:8010 (demo labels only)
$env:NEURON_CLASSIFIER_URLS = "http://127.0.0.1:8010/classify"
```

The Next.js dev server on `http://localhost:3000` talks to it directly; see
`docs/API_CONTRACT.md` for CORS/cookie rules.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEURON_CLASSIFIER_URLS` | — | comma-separated POST endpoints, tried in order; empty = in-process DEMO classifier |
| `NEURON_MOCK_DELAY_SECONDS` | `1.0` | artificial delay of the in-process DEMO classifier |
| `NEURON_CLASSIFIER_MODE` | `csv` | `csv` = multipart upload, `rows` = JSON rows |
| `NEURON_CLASSIFIER_FIELD_NAME` | `file` | multipart file field name |
| `NEURON_CLASSIFIER_TIMEOUT_SECONDS` | `1800` | per-request timeout, capped by the job deadline |
| `NEURON_CLASSIFIER_RETRIES` | `0` | retries per endpoint (long requests are not retried by default) |
| `NEURON_CLASSIFIER_TOKEN` | — | optional `Authorization: Bearer` token |
| `NEURON_TEMP_DIR` | system temp | dataset snapshots, job outputs |
| `NEURON_JOB_DEADLINE_SECONDS` | `1800` | job budget; `ARENA_DEADLINE` also caps it |
| `NEURON_RESULT_GRACE_SECONDS` | `600` | result kept downloadable after completion |

The API runs one global job at a time; this limit is fixed and has no environment setting.

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
      mock_engine.py     in-process DEMO classifier (default when no URL is set)
      processor.py       snapshot -> remote request -> validated output table
      cli.py             standalone processor entry point
    mock_classifier.py   local demo stand-in for the teammates' service
  tests/                 engine + API + end-to-end tests
  docs/                  API_CONTRACT.md, DECISIONS.md
```
