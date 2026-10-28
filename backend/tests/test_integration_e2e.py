"""End-to-end acceptance: real FastAPI app + real processor + HTTP classifier client.

The teammates' classification service is simulated with httpx.MockTransport so the
whole pipeline (session -> bulk dataset -> mapping -> async job -> events/results ->
CSV export) is exercised without network. TestClient is used as a context manager
on purpose: the job runs as an asyncio task on the app's request-scoped loop.
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

SAMPLE_CSV = (
    "id,text,date,label\n"
    "s-1,Hooly AI Pro costs EUR 59 a month.,2026-04-20,\n"
    "s-2,Holdan started at Hooly on 12 January 2026.,2026-01-12,\n"
    "s-3,The Hooly Gemini launch happened in 2026.,2026-02-01,\n"
    "s-4,\"A quoted, comma and \"\"quote\"\" inside\",2026-03-01,\n"
    "s-5,,2026-04-01,\n"
)

MAPPING = {"textColumn": "text", "dateColumn": "date", "idColumn": "id", "resultColumn": "label"}


def make_client(tmp_path: Path):
    from app.config import get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    settings = replace(get_settings(), temp_dir=tmp_path / "tmp", data_dir=DATA_DIR)
    return TestClient(create_app(settings))


def install_fake_service(monkeypatch, handler) -> None:
    import app.api.jobs as jobs_module
    from app.engine.remote_engine import RemoteClassifierEngine

    transport = httpx.MockTransport(handler)

    def factory(_data_dir):
        return RemoteClassifierEngine(
            ["http://classifier.test/classify"], mode="rows", transport=transport
        )

    monkeypatch.setattr(jobs_module, "engine_factory", factory)


def wait_for_terminal(client, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"/api/v1/jobs/{job_id}").json()
        if snapshot.get("status") in ("succeeded", "failed"):
            return snapshot
        time.sleep(0.1)
    pytest.fail(f"job did not finish in {timeout}s: {snapshot}")


def prepare_job(client) -> tuple[str, str]:
    uploaded = client.post(
        "/api/v1/datasets/bulk",
        files={"file": ("universe.csv", SAMPLE_CSV.encode("utf-8"), "text/csv")},
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


def test_remote_classification_pipeline(monkeypatch, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        ids = [row["id"] for row in payload["rows"]]
        assert ids == ["s-1", "s-2", "s-3", "s-4", "s-5"]
        return httpx.Response(200, content=json.dumps({"results": [
            {"id": "s-1", "label": "true", "confidence": 0.9},
            {"id": "s-2", "label": "false", "confidence": 0.7},
            {"id": "s-3", "label": "unsure"},
            {"id": "s-4", "label": "true", "confidence": 0.6},
        ]}).encode())

    install_fake_service(monkeypatch, handler)
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
        counters = terminal["counters"]
        assert counters["true"] == 2 and counters["false"] == 1 and counters["unsure"] == 1
        assert counters["fallback"] == 1

        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200, summary.text
        assert summary.json()["totalRows"] == 5

        events = client.get(f"/api/v1/jobs/{job_id}/events?limit=1000").json()
        assert events["events"], "no events recorded"
        assert events["events"][0]["type"] == "job.started"
        assert [event["sequenceId"] for event in events["events"]] == sorted(event["sequenceId"] for event in events["events"])
        assert events["events"][-1]["type"] in ("job.completed", "job.failed")

        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200, output.text
        assert output.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert [row["id"] for row in rows] == ["s-1", "s-2", "s-3", "s-4", "s-5"]
        assert [row["label"] for row in rows] == ["true", "false", "unsure", "true", "unsure"]
        assert rows[3]["text"] == 'A quoted, comma and "quote" inside'

        errors = client.get(f"/api/v1/jobs/{job_id}/result/errors").json()
        assert errors["total"] == 1
        assert errors["items"][0]["rowId"] == "s-5"
        assert errors["items"][0]["code"] == "REMOTE_MISSING_RESULT"

        preview = client.get(f"/api/v1/jobs/{job_id}/result/preview?limit=2").json()
        assert preview["columns"][:4] == ["id", "text", "date", "label"]
        assert len(preview["rows"]) == 2

        with make_client(tmp_path / "other") as other:
            other.post("/api/v1/sessions")
            assert other.get(f"/api/v1/jobs/{job_id}").status_code == 404
            assert other.get(f"/api/v1/jobs/{job_id}/result.csv").status_code == 404


def test_unavailable_classifier_fails_the_job_honestly(monkeypatch, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    install_fake_service(monkeypatch, handler)
    with make_client(tmp_path) as client:
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


def test_semicolon_bulk_is_normalised_before_the_job(monkeypatch, tmp_path: Path):
    semicolon = (
        "id;text;date;label\n"
        "c-1;Hooly AI Pro costs EUR 59 a month.;2026-04-20;\n"
        "c-2;Holdan started at Hooly on 12 January 2026.;2026-01-12;\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["columns"] == ["id", "text", "date", "label"]
        assert payload["rows"][0]["text"] == "Hooly AI Pro costs EUR 59 a month."
        return httpx.Response(200, content=json.dumps({"results": [
            {"id": "c-1", "label": "true", "confidence": 0.9},
            {"id": "c-2", "label": "false", "confidence": 0.8},
        ]}).encode())

    install_fake_service(monkeypatch, handler)
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

        confirmed = client.put(f"/api/v1/datasets/{dataset['id']}/mapping", json=MAPPING)
        assert confirmed.status_code == 200, confirmed.text
        started = client.post("/api/v1/jobs", json={"datasetId": dataset["id"]})
        assert started.status_code == 202, started.text
        terminal = wait_for_terminal(client, started.json()["job"]["id"])
        assert terminal["status"] == "succeeded", terminal
        output = client.get(f"/api/v1/jobs/{terminal['id']}/result.csv")
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert [row["id"] for row in rows] == ["c-1", "c-2"]
        assert [row["label"] for row in rows] == ["true", "false"]


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