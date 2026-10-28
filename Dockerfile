FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/cache

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir joblib==1.5.3 lightgbm==4.6.0 numpy==2.2.6 scipy==1.15.3 scikit-learn==1.6.1
COPY backend /app/backend
COPY data /app/data
COPY scripts/run_arena.py /app/scripts/run_arena.py

USER 10001
CMD ["python", "/app/scripts/run_arena.py"]
