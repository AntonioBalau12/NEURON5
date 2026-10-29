"""End-to-end acceptance through the real local model and FastAPI app."""

from __future__ import annotations

import csv
import io
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.engine.api import RowInput
from app.engine.local_engine import LocalModelEngine
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = REPO_ROOT / "backend" / "scripts" / "adapter.joblib"
FINAL_MODEL_PATH = REPO_ROOT / "ml/classical/results_m2_v2/model.joblib"

SAMPLE_ROWS = [
    ["s-1", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20", ""],
    ["s-2", "Holdan started at Hooly on 12 January 2026.", "2026-01-12", ""],
    ["s-3", "The Hooly Gemini launch happened in 2026.", "2026-02-01", ""],
    ["s-4", 'A quoted, comma and "quote" inside', "2026-03-01", ""],
    ["s-5", "", "2026-04-01", ""],
]
SAMPLE_CSV = (
    "id,text,date,label\n"
    "s-1,Hooly AI Pro costs EUR 59 a month.,2026-04-20,\n"
    "s-2,Holdan started at Hooly on 12 January 2026.,2026-01-12,\n"
    "s-3,The Hooly Gemini launch happened in 2026.,2026-02-01,\n"
    's-4,"A quoted, comma and ""quote"" inside",2026-03-01,\n'
    "s-5,,2026-04-01,\n"
)
MAPPING = {"textColumn": "text", "dateColumn": "date", "idColumn": "id", "resultColumn": "label"}


@pytest.fixture(scope="module")
def local_engine():
    engine = LocalModelEngine(MODEL_PATH)
    engine.prepare()
    yield engine
    engine.close()


def make_client(tmp_path: Path, *, model_path: Path = MODEL_PATH):
    settings = replace(
        get_settings(), temp_dir=tmp_path / "tmp", model_path=model_path
    )
    return TestClient(create_app(settings))


def wait_for_terminal(client, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"/api/v1/jobs/{job_id}").json()
        if snapshot.get("status") in ("succeeded", "failed"):
            return snapshot
        time.sleep(0.1)
    pytest.fail(f"job did not finish in {timeout}s: {snapshot}")


def prepare_job(client, *, csv_text: str = SAMPLE_CSV) -> tuple[str, str]:
    uploaded = client.post(
        "/api/v1/datasets/bulk",
        files={"file": ("universe.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    confirmed = client.put(f"/api/v1/datasets/{dataset['id']}/mapping", json=MAPPING)
    assert confirmed.status_code == 200, confirmed.text
    started = client.post(
        "/api/v1/jobs",
        json={"datasetId": dataset["id"]},
        headers={"Idempotency-Key": "e2e-key-1"},
    )
    assert started.status_code == 202, started.text
    return dataset["id"], started.json()["job"]["id"]


def expected_label(engine: LocalModelEngine, text: str, date: str) -> str:
    decision = engine.classify(RowInput("expected", text, date))
    return decision.label


def test_local_classification_pipeline(local_engine, tmp_path: Path):
    with make_client(tmp_path) as client:
        assert client.get("/api/v1/sessions/current").status_code == 401
        assert client.post("/api/v1/sessions").status_code in (200, 201)

        dataset_id, job_id = prepare_job(client)
        replayed = client.post(
            "/api/v1/jobs",
            json={"datasetId": dataset_id},
            headers={"Idempotency-Key": "e2e-key-1"},
        )
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["job"]["id"] == job_id
        assert replayed.json()["replayed"] is True

        terminal = wait_for_terminal(client, job_id)
        assert terminal["status"] == "succeeded", terminal
        assert terminal["resultAvailable"] is True
        expected = [
            expected_label(local_engine, row[1], row[2]) if row[1].strip() else "unsure"
            for row in SAMPLE_ROWS
        ]
        counters = terminal["counters"]
        assert counters["true"] == expected.count("true")
        assert counters["false"] == expected.count("false")
        assert counters["unsure"] == sum(
            label == "unsure" and bool(row[1].strip())
            for row, label in zip(SAMPLE_ROWS, expected, strict=True)
        )
        assert counters["fallback"] == 1

        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200, summary.text
        assert summary.json()["totalRows"] == 5

        events = client.get(f"/api/v1/jobs/{job_id}/events?limit=1000").json()
        assert events["events"], "no events recorded"
        assert events["events"][0]["type"] == "job.started"
        sequences = [event["sequenceId"] for event in events["events"]]
        assert sequences == sorted(sequences)
        assert events["events"][-1]["type"] in ("job.completed", "job.failed")

        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200, output.text
        assert output.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert [row["id"] for row in rows] == [row[0] for row in SAMPLE_ROWS]
        assert [row["label"] for row in rows] == expected
        assert rows[3]["text"] == 'A quoted, comma and "quote" inside'

        errors = client.get(f"/api/v1/jobs/{job_id}/result/errors").json()
        assert errors["total"] == 1
        assert errors["items"][0]["rowId"] == "s-5"
        assert errors["items"][0]["code"] == "EMPTY_TEXT"

        preview = client.get(f"/api/v1/jobs/{job_id}/result/preview?limit=2").json()
        assert preview["columns"][:4] == ["id", "text", "date", "label"]
        assert len(preview["rows"]) == 2

        with make_client(tmp_path / "other") as other:
            other.post("/api/v1/sessions")
            assert other.get(f"/api/v1/jobs/{job_id}").status_code == 404
            assert other.get(f"/api/v1/jobs/{job_id}/result.csv").status_code == 404


def test_missing_model_fails_the_job_honestly(tmp_path: Path):
    with make_client(tmp_path, model_path=tmp_path / "missing.joblib") as client:
        client.post("/api/v1/sessions")
        _, job_id = prepare_job(client)

        terminal = wait_for_terminal(client, job_id)
        assert terminal["status"] == "failed", terminal
        assert terminal["failureReason"] == "CLASSIFIER_UNAVAILABLE"
        assert terminal["resultAvailable"] is False
        assert client.get(f"/api/v1/jobs/{job_id}/result.csv").status_code in (404, 409)

        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200
        assert summary.json()["failureReason"] == "CLASSIFIER_UNAVAILABLE"


def test_final_m2_pipeline_runs_through_web_api(tmp_path: Path):
    engine = LocalModelEngine(FINAL_MODEL_PATH)
    assert len(engine.adapter.extractor.retriever.graph.entities) == 62
    with make_client(tmp_path, model_path=FINAL_MODEL_PATH) as client:
        client.post("/api/v1/sessions")
        _, job_id = prepare_job(client)
        terminal = wait_for_terminal(client, job_id)
        assert terminal["status"] == "succeeded", terminal
        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert len(rows) == len(SAMPLE_ROWS)
        assert [row["label"] for row in rows] == [
            expected_label(engine, row[1], row[2]) for row in SAMPLE_ROWS
        ]
        assert terminal["counters"]["errors"] == 1


def test_semicolon_bulk_is_normalised_before_local_classification(local_engine, tmp_path: Path):
    semicolon = (
        "id;text;date;label\n"
        "c-1;Hooly AI Pro costs EUR 59 a month.;2026-04-20;\n"
        "c-2;Holdan started at Hooly on 12 January 2026.;2026-01-12;\n"
    )
    with make_client(tmp_path) as client:
        client.post("/api/v1/sessions")
        uploaded = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("semicolon.csv", semicolon.encode("utf-8"), "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        dataset = uploaded.json()
        assert dataset["delimiter"] == ";"
        assert dataset["columns"] == ["id", "text", "date", "label"]
        assert client.put(f"/api/v1/datasets/{dataset['id']}/mapping", json=MAPPING).status_code == 200
        started = client.post("/api/v1/jobs", json={"datasetId": dataset["id"]})
        assert started.status_code == 202, started.text
        job_id = started.json()["job"]["id"]
        terminal = wait_for_terminal(client, job_id)
        assert terminal["status"] == "succeeded", terminal
        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert [row["id"] for row in rows] == ["c-1", "c-2"]
        assert [row["label"] for row in rows] == [
            expected_label(local_engine, "Hooly AI Pro costs EUR 59 a month.", "2026-04-20"),
            expected_label(local_engine, "Holdan started at Hooly on 12 January 2026.", "2026-01-12"),
        ]


def test_manual_dataset_validation_limits(tmp_path: Path):
    with make_client(tmp_path) as client:
        client.post("/api/v1/sessions")

        empty = client.post("/api/v1/datasets/manual", json={"columns": ["id", "text", "date"], "rows": []})
        assert empty.status_code == 201, empty.text
        assert empty.json()["rowCount"] == 0

        oversized = client.post(
            "/api/v1/datasets/manual",
            json={"columns": ["id", "text", "date"], "rows": [["r-1", "x" * 1_100_000, "2026-01-01"]]},
        )
        assert oversized.status_code == 413, oversized.text
        assert oversized.json()["error"]["code"] == "DATASET_TOO_LARGE"

        good = client.post(
            "/api/v1/datasets/manual",
            json={"columns": ["id", "text", "date"], "rows": [["r-1", "Hooly Cloud was launched.", "2026-01-01"]]},
        )
        assert good.status_code == 201, good.text
        assert good.json()["mapping"]["textColumn"] == "text"

        bad_mapping = client.put(
            f"/api/v1/datasets/{good.json()['id']}/mapping",
            json={"textColumn": "nope", "dateColumn": None, "idColumn": None, "resultColumn": "label"},
        )
        assert bad_mapping.status_code == 400
        assert bad_mapping.json()["error"]["code"] == "INVALID_MAPPING"
