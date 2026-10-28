"""First-class support for the exact input schema: id,text,date,label,form."""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from app.engine.api import RowInput
from app.engine.local_engine import LocalModelEngine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = BACKEND_ROOT / "scripts" / "adapter.joblib"

PRACTICE_COLUMNS = ["id", "text", "date", "label", "form"]
FORM_1 = json.dumps([{"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": "2026-01-12"}}])
FORM_2 = json.dumps([{"subject": "Hooly AI Pro", "attribute": "price", "value": {"kind": "money", "value": 59, "currency": "EUR", "per": "month"}}])
FORM_3 = "[]"  # empty form is valid


def practice_csv(rows=None) -> bytes:
    rows = rows or [
        ["p-1", "Holdan started at Hooly on 12 January 2026.", "2026-01-12", "", FORM_1],
        ["p-2", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20", "true", FORM_2],
        ["p-3", "Hooly no longer sells the tablet.", "2026-05-10", "", FORM_3],
        ["p-4", "Hooly might launch a server.", "2026-06-01", "", "[]"],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(PRACTICE_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def make_client(tmp_path: Path):
    from app.config import get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    settings = replace(get_settings(), temp_dir=tmp_path / "tmp", model_path=MODEL_PATH)
    return TestClient(create_app(settings))


@pytest.fixture(scope="module")
def local_engine():
    engine = LocalModelEngine(MODEL_PATH)
    engine.prepare()
    yield engine
    engine.close()


def test_practice_upload_detects_schema_and_confirms_mapping(tmp_path: Path):
    with make_client(tmp_path) as client:
        client.post("/api/v1/sessions")
        uploaded = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("practice.csv", practice_csv(), "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        dataset = uploaded.json()
        assert dataset["format"] == "practice"
        assert dataset["columns"] == PRACTICE_COLUMNS
        assert dataset["mapping"] == {
            "textColumn": "text",
            "dateColumn": "date",
            "idColumn": "id",
            "resultColumn": "label",
            "confirmed": True,
            "autoDetected": True,
        }
        assert dataset["warnings"] == []
        # form JSON survives the snapshot normalisation byte-for-byte as a CSV value
        assert dataset["preview"]["rows"][0][4] == FORM_1
        assert dataset["preview"]["rows"][1][4] == FORM_2


def test_practice_rows_are_validated_and_reported(tmp_path: Path):
    rows = [
        ["p-1", "ok sentence", "2026-13-40", "", "[]"],          # bad date
        ["p-2", "ok sentence", "2026-01-12", "maybe", "[]"],      # bad label
        ["p-3", "", "2026-01-12", "", "not json"],                # empty text + bad form
    ]
    with make_client(tmp_path) as client:
        client.post("/api/v1/sessions")
        uploaded = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("practice.csv", practice_csv(rows), "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        dataset = uploaded.json()
        assert dataset["format"] == "practice"
        assert "PRACTICE_ROW_ERRORS" in dataset["warnings"]


def test_practice_job_uses_local_model_and_preserves_schema(local_engine, tmp_path: Path):
    rows = [
        ["p-1", "Holdan started at Hooly on 12 January 2026.", "2026-01-12", "", FORM_1],
        ["p-2", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20", "stale", FORM_2],
        ["p-3", "Hooly no longer sells the tablet.", "2026-05-10", "", FORM_3],
        ["p-4", "Hooly might launch a server.", "2026-06-01", "", "[]"],
    ]
    with make_client(tmp_path) as client:
        client.post("/api/v1/sessions")
        uploaded = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("practice.csv", practice_csv(rows), "text/csv")},
        )
        dataset = uploaded.json()
        # mapping is already confirmed by the practice-format detector
        started = client.post("/api/v1/jobs", json={"datasetId": dataset["id"]})
        assert started.status_code == 202, started.text
        job_id = started.json()["job"]["id"]
        deadline = time.time() + 30
        snapshot = {}
        while time.time() < deadline:
            snapshot = client.get(f"/api/v1/jobs/{job_id}").json()
            if snapshot["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert snapshot["status"] == "succeeded", snapshot

        expected = [
            local_engine.classify(RowInput(row[0], row[1], row[2])).label
            for row in rows
        ]
        assert snapshot["counters"]["true"] == expected.count("true")
        assert snapshot["counters"]["false"] == expected.count("false")
        assert snapshot["counters"]["unsure"] == expected.count("unsure")

        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200
        parsed = list(csv.DictReader(io.StringIO(output.text)))
        assert list(parsed[0].keys()) == PRACTICE_COLUMNS
        source_forms = [row[4] for row in rows]
        assert [row["form"] for row in parsed] == source_forms
        assert [row["id"] for row in parsed] == ["p-1", "p-2", "p-3", "p-4"]
        assert [row["label"] for row in parsed] == expected
        assert parsed[1]["label"] != "stale"
