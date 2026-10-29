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
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/frontend/.next/cache \
    && chown -R 10001:10001 /app/frontend
COPY backend/requirements-runtime.txt /app/backend/requirements-runtime.txt
RUN pip install --no-cache-dir -r /app/backend/requirements-runtime.txt
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-build --chown=10001:10001 /app/frontend/.next/standalone/ /app/frontend/
COPY --from=frontend-build --chown=10001:10001 /app/frontend/.next/static/ /app/frontend/.next/static/
COPY --from=frontend-build --chown=10001:10001 /app/frontend/public/ /app/frontend/public/
COPY backend /app/backend
COPY data/practice.csv data/lexicon.json /app/data/
COPY foundation.py runner.py /app/
COPY core /app/core
COPY ml/classical/*.py /app/ml/classical/
COPY ml/classical/results_m2_v2/model.joblib /app/ml/classical/results_m2_v2/model.joblib
COPY contracts /app/contracts
COPY scripts/build_reference_graph.py /app/scripts/build_reference_graph.py
RUN python /app/scripts/build_reference_graph.py
COPY scripts/start.py /app/scripts/start.py

EXPOSE 3000 8000
USER 10001
CMD ["python", "/app/scripts/start.py"]
