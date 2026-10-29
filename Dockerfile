FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --non-interactive
COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN yarn build

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache \
    NEURON_MODE=arena \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PYTHONPATH=/app:/app/backend

WORKDIR /app
COPY backend/requirements-runtime.txt /app/backend/requirements-runtime.txt
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /app/backend/requirements-runtime.txt
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-build --chown=10001:10001 /app/frontend/.next/standalone/ /app/frontend/
COPY --from=frontend-build --chown=10001:10001 /app/frontend/.next/static/ /app/frontend/.next/static/
COPY --from=frontend-build --chown=10001:10001 /app/frontend/public/ /app/frontend/public/
COPY backend /app/backend
COPY data /app/data
COPY core /app/core
COPY ml /app/ml
COPY foundation.py runner.py /app/
COPY contracts /app/contracts
COPY scripts/run_arena.py /app/scripts/run_arena.py
RUN python -c "from pathlib import Path; from core.graph.reference import write_reference_snapshot; print(write_reference_snapshot(Path('/app/artifacts/reference_graph.pkl'), Path('/app/data/practice.csv'), Path('/app/data/lexicon.json')))"

USER 10001
EXPOSE 3000 8000
ENTRYPOINT ["sh", "-c", "if [ \"$NEURON_MODE\" = web ]; then python -m uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port 8000 & exec node /app/frontend/server.js; else csv=/universe/universe.csv; lexicon=/universe/lexicon.json; for arg do case \"$arg\" in --csv=*) csv=${arg#--csv=}; lexicon=/app/data/lexicon.json;; *) echo \"unknown argument: $arg\" >&2; exit 2;; esac; done; python /app/runner.py --universe \"$csv\" --lexicon \"$lexicon\" --output /output/output.csv; status=$?; chmod 0644 /output/output.csv 2>/dev/null || true; exit \"$status\"; fi", "docker-entrypoint"]
