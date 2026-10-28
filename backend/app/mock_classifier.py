"""Local stand-in for the teammates' HTTP classification service.

It accepts the same payloads the backend sends (multipart CSV in "csv" mode,
JSON rows in "rows" mode) and answers with the labelled table. The labels are
DEMO PLACEHOLDERS, not real classification: this mock exists so the UI, job
orchestration and result pipeline can be exercised while the team service is
not running. Replace it by pointing NEURON_CLASSIFIER_URLS at the real service.

  cd backend
  python -m app.mock_classifier          # http://127.0.0.1:8010
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="NEURON5 mock classification service", version="0.1.0")

FALSE_CUES = (" not ", " never ", " no longer", "discontinu", "cancel", "drops ", "slashes ")
UNSURE_CUES = ("may ", "might ", "could ", "probably ", "rumour", "rumor", "reportedly")


def mock_label(text: str) -> tuple[str, float | None]:
    lowered = f" {text.strip().lower()} "
    if not text.strip():
        return "unsure", None
    if any(cue in lowered for cue in FALSE_CUES):
        return "false", 0.55
    if any(cue in lowered for cue in UNSURE_CUES):
        return "unsure", None
    return "true", 0.6


def _fill_csv(data: bytes, result_column: str) -> bytes:
    text = data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows:
        raise ValueError("empty CSV")
    header = rows[0]
    text_index = 1
    for index, name in enumerate(header):
        if name.strip().lower() in ("text", "sentence", "proposition", "claim"):
            text_index = index
            break
    try:
        result_index = [name.strip().lower() for name in header].index(result_column.lower())
    except ValueError:
        result_index = None
        header = header + [result_column]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    for row in rows[1:]:
        if not row:
            continue
        if len(row) < len(header) - (0 if result_index is not None else 1):
            row = row + [""] * (len(header) - len(row))
        sentence = row[text_index] if text_index < len(row) else ""
        label, _ = mock_label(sentence)
        if result_index is None:
            row = row + [label]
        else:
            if result_index >= len(row):
                row = row + [""] * (result_index - len(row) + 1)
            row[result_index] = label
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


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
        result_column = str(form.get("resultColumn") or "label")
        try:
            output = _fill_csv(data, result_column)
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
    for index, row in enumerate(rows):
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
