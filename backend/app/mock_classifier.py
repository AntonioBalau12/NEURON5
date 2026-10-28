"""Local stand-in for the teammates' HTTP classification service.

It accepts the same payloads the backend sends (multipart CSV in "csv" mode,
JSON rows in "rows" mode) and answers with the labelled table. The labels are
DEMO PLACEHOLDERS, not real classification. Use it to exercise the real HTTP
client path:

  cd backend
  python -m app.mock_classifier          # http://127.0.0.1:8010
  # then start the API with:
  # NEURON_CLASSIFIER_URLS=http://127.0.0.1:8010/classify uvicorn app.main:app

Without NEURON_CLASSIFIER_URLS the API does not need this process: it uses the
same demo heuristic in-process (app/engine/mock_engine.py).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .engine.mock_engine import fill_csv_with_mock_labels, mock_label

app = FastAPI(title="NEURON5 mock classification service", version="0.2.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "mock-classifier", "note": "demo labels, not real classification"}


@app.post("/classify")
async def classify(request: Request) -> Response:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = None
        for key in ("file", "csv", "dataset"):
            if key in form:
                upload = form[key]
                break
        if upload is None:
            return JSONResponse({"error": "no file field in multipart payload"}, status_code=400)
        data = await upload.read() if hasattr(upload, "read") else bytes(upload)
        mapping_raw = form.get("mapping")
        mapping: dict[str, Any] = {}
        if isinstance(mapping_raw, str) and mapping_raw:
            try:
                parsed = json.loads(mapping_raw)
                if isinstance(parsed, dict):
                    mapping = parsed
            except ValueError:
                mapping = {}
        result_column = str(mapping.get("resultColumn") or form.get("resultColumn") or "label")
        text_column = mapping.get("textColumn")
        try:
            output, _columns, _rows, _counts = fill_csv_with_mock_labels(
                data, result_column=result_column, text_column=str(text_column) if text_column else None
            )
        except (ValueError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": f"cannot parse uploaded CSV: {exc}"}, status_code=400)
        return Response(content=output, media_type="text/csv; charset=utf-8")

    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"error": "expected multipart CSV or JSON payload"}, status_code=400)
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return JSONResponse({"error": "expected a rows array"}, status_code=400)
    mapping = payload.get("mapping", {}) if isinstance(payload, dict) else {}
    result_column = str(mapping.get("resultColumn") or "label")
    answer: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            return JSONResponse({"error": "rows must be objects"}, status_code=400)
        sentence = str(row.get("text") or row.get("sentence") or "")
        label, confidence = mock_label(sentence)
        if set(row).issubset({"id", "text", "date"}):
            answer.append({"id": row.get("id"), "label": label, "confidence": confidence})
        else:
            merged = dict(row)
            merged[result_column] = label
            answer.append(merged)
    return JSONResponse({"rows": answer})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
