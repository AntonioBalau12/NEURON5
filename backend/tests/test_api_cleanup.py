"""Lifespan cleanup: expired sessions and terminal jobs after the grace period."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.api.utils import utcnow
from test_api_helpers import (
    FakeProcessor,
    create_session,
    install_fake,
    make_app,
    manual_dataset,
    post_job,
    prepared_dataset,
    wait_until,
)

ROWS = [
    ["p-1", "This yes happened", "2026-01-01"],
    ["p-2", "This no happened", "2026-01-02"],
]


def test_terminal_job_and_dataset_are_removed_after_grace(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.2))
    app = make_app(tmp_path, result_grace_seconds=0, cleanup_interval_seconds=0.05)
    state = app.state.n5
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        output_path = state.jobs[job_id].output_path
        wait_until(
            lambda: job_id not in state.jobs
            and dataset["id"] not in state.datasets
            and not output_path.exists()
        )
        wait_until(lambda: client.get(f"/api/v1/jobs/{job_id}").status_code == 404)
        assert job_id not in state.jobs
        assert dataset["id"] not in state.datasets
        assert job_id not in state.event_logs
        assert not output_path.exists()
        assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 404
        assert (
            client.get(f"/api/v1/jobs/{job_id}/result/summary").status_code == 404
        )
    assert not state.run_dir.exists()


def test_expired_session_is_dropped_with_its_resources(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path, cleanup_interval_seconds=0.05)
    state = app.state.n5
    with TestClient(app) as client:
        session = create_session(client)
        dataset = manual_dataset(client, ROWS)
        session_id = session["sessionId"]
        state.sessions[session_id].expires_at = utcnow() - timedelta(seconds=1)
        wait_until(lambda: session_id not in state.sessions)
        assert dataset["id"] not in state.datasets
        assert state.tokens == {}
        assert client.get("/api/v1/sessions/current").status_code == 401
