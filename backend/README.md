# Backend — NEURON5 local CSV classification API

FastAPI service for the three-stage UI in `../frontend`. The backend runs the
calibrated M2 v2 pipeline stored in `../ml/classical/results_m2_v2/model.joblib`.
Classification uses the preloaded reference graph, BM25 retrieval, text/date
features and the artifact's calibrated decision policy, with two LightGBM threads.
No HTTP classifier service or LLM is used. The web API classifies uploaded rows;
full P3 claim generation and anytime publication run through the Docker `arena` mode.

## Run locally

Use Python 3.12 in an isolated environment. On Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Linux, create the same environment with `python3 -m venv .venv` and use
`.venv/bin/python` for installation, startup, CLI processing and tests below.

The default model path is `ml/classical/results_m2_v2/model.joblib` at the repository root.
To use another compatible artifact, set `NEURON_MODEL_PATH` before starting the API.
The previous `backend/scripts/adapter.joblib` remains supported as an explicit override.
The Docker runtime pins scikit-learn 1.9.1 to match the final M2 artifact.
For local development, install the updated requirements before starting the API.
The loaded model is cached per process and path; restart the backend after
replacing an artifact at the same path. If the artifact is missing or cannot be
loaded, jobs fail with `CLASSIFIER_UNAVAILABLE`; the backend does not substitute
placeholder labels.

The Next.js development server at `http://localhost:3000` talks to the API;
see `docs/API_CONTRACT.md` for the routes, CORS and cookie rules.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEURON_MODEL_PATH` | `ml/classical/results_m2_v2/model.joblib` | Calibrated M2 model artifact |
| `NEURON_TEMP_DIR` | system temp | Dataset snapshots and job outputs |
| `NEURON_JOB_DEADLINE_SECONDS` | `1800` | Job budget; `ARENA_DEADLINE` can cap it |
| `NEURON_RESULT_GRACE_SECONDS` | `600` | Time results remain downloadable after completion |

The API runs one global job at a time; this limit is fixed.

## CLI

Run the same local row processor without starting FastAPI:

```sh
cd backend
python -m app.engine.cli --input ../data/practice.csv --output /tmp/out.csv
```

Use `--model <path>` to select another compatible artifact and
`--deadline-seconds <seconds>` to set a CLI deadline. `ARENA_DEADLINE` also
caps the deadline. The CLI writes the labeled CSV to the requested output path.

## Tests

```sh
cd backend && python -m pytest -q
```

## Layout

```text
backend/
  app/
    config.py            settings (model path, limits and deadlines)
    main.py              FastAPI app factory + CORS + lifespan
    api/                 sessions, datasets, jobs, events and results routers
    engine/
      api.py             Engine/MappingSpec/processor interface
      model_engine.py    local adapter loading and row inference
      processor.py       CSV snapshot -> row inference -> validated output
      cli.py             standalone local processor entry point
  scripts/
    adapter.joblib       fitted local prototype classifier
  tests/                 engine and API tests
  docs/                  API_CONTRACT.md, DECISIONS.md
```
