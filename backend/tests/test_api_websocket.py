"""WebSocket stream: handshake, snapshot, replay, gap, live and rejects."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import events as events_module
from test_api_helpers import (
    FakeProcessor,
    create_session,
    install_fake,
    make_app,
    post_job,
    prepared_dataset,
    wait_for_terminal,
)

ROWS = [
    ["p-1", "This yes happened", "2026-01-01"],
    ["p-2", "This no happened", "2026-01-02"],
    ["p-3", "broken row", "2026-01-03"],
    ["p-4", "Maybe later", "2026-01-04"],
]


def _completed_job(client: TestClient) -> tuple[str, list[dict]]:
    dataset = prepared_dataset(client, ROWS)
    job_id = post_job(client, dataset["id"]).json()["job"]["id"]
    wait_for_terminal(client, job_id)
    events = client.get(f"/api/v1/jobs/{job_id}/events?limit=1000").json()
    return job_id, events["events"]


def _drain_events(ws) -> list[dict]:
    received: list[dict] = []
    while True:
        try:
            frame = ws.receive_json()
        except WebSocketDisconnect as exc:
            assert exc.code == 1000
            break
        if frame["kind"] == "event":
            received.append(frame["event"])
        elif frame["kind"] == "heartbeat":
            continue
        else:  # pragma: no cover - protocol guard
            raise AssertionError(f"unexpected frame {frame!r}")
    return received


def test_websocket_handshake_snapshot_and_replay(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        job_id, events = _completed_job(client)
        last_sequence = events[-1]["sequenceId"]

        with client.websocket_connect(
            f"/api/v1/jobs/{job_id}/stream?lastSequenceId=0"
        ) as ws:
            handshake = ws.receive_json()
            assert handshake["kind"] == "handshake"
            assert handshake["protocolVersion"] == 1
            assert handshake["jobId"] == job_id
            assert handshake["status"] == "succeeded"
            assert handshake["lastSequenceId"] == last_sequence
            assert handshake["replayAvailable"] is True
            assert handshake["serverTime"].endswith("Z")

            snapshot = ws.receive_json()
            assert snapshot["kind"] == "snapshot"
            assert snapshot["gap"] is False
            assert snapshot["replayFrom"] == 1
            assert snapshot["job"]["id"] == job_id
            assert snapshot["job"]["status"] == "succeeded"

            replayed = _drain_events(ws)
        assert [event["sequenceId"] for event in replayed] == list(
            range(1, last_sequence + 1)
        )
        assert replayed[0]["type"] == "job.started"
        assert replayed[-1]["type"] == "job.completed"


def test_websocket_replay_resumes_after_last_sequence(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        job_id, events = _completed_job(client)
        requested = 2
        with client.websocket_connect(
            f"/api/v1/jobs/{job_id}/stream?lastSequenceId={requested}"
        ) as ws:
            handshake = ws.receive_json()
            assert handshake["replayAvailable"] is True
            snapshot = ws.receive_json()
            assert snapshot["gap"] is False
            assert snapshot["replayFrom"] == requested + 1
            replayed = _drain_events(ws)
        assert replayed
        assert all(event["sequenceId"] > requested for event in replayed)
        assert replayed[0]["sequenceId"] == requested + 1


def test_websocket_gap_when_buffer_dropped_events(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path, event_buffer_size=3)
    with TestClient(app) as client:
        create_session(client)
        job_id, events = _completed_job(client)
        assert len(events) == 3
        oldest = events[0]["sequenceId"]
        last_sequence = events[-1]["sequenceId"]
        history = client.get(f"/api/v1/jobs/{job_id}/events?afterSequenceId=0").json()
        assert history["truncated"] is True

        with client.websocket_connect(
            f"/api/v1/jobs/{job_id}/stream?lastSequenceId=0"
        ) as ws:
            handshake = ws.receive_json()
            assert handshake["lastSequenceId"] == last_sequence
            assert handshake["replayAvailable"] is False
            snapshot = ws.receive_json()
            assert snapshot["gap"] is True
            assert snapshot["replayFrom"] == oldest
            replayed = _drain_events(ws)
        assert [event["sequenceId"] for event in replayed] == list(
            range(oldest, last_sequence + 1)
        )
        assert client.get(f"/api/v1/jobs/{job_id}/events?afterSequenceId=0").json()[
            "truncated"
        ] is True


def test_websocket_live_events_and_disconnect_does_not_stop_job(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.5))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        with client.websocket_connect(
            f"/api/v1/jobs/{job_id}/stream?lastSequenceId=0"
        ) as ws:
            handshake = ws.receive_json()
            assert handshake["kind"] == "handshake"
            assert handshake["jobId"] == job_id
            snapshot = ws.receive_json()
            assert snapshot["kind"] == "snapshot"
            event_frame = ws.receive_json()
            assert event_frame["kind"] == "event"
            assert event_frame["event"]["jobId"] == job_id
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded"
        assert job["resultAvailable"] is True


def test_websocket_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(events_module, "HEARTBEAT_SECONDS", 0.05)
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.4))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        with client.websocket_connect(
            f"/api/v1/jobs/{job_id}/stream?lastSequenceId=0"
        ) as ws:
            assert ws.receive_json()["kind"] == "handshake"
            assert ws.receive_json()["kind"] == "snapshot"
            heartbeat = None
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                frame = ws.receive_json()
                if frame["kind"] == "heartbeat":
                    heartbeat = frame
                    break
            assert heartbeat is not None
            assert heartbeat["serverTime"].endswith("Z")
            assert "sequenceId" not in heartbeat
        wait_for_terminal(client, job_id)


def _ws_close_code(client: TestClient, url: str, headers: dict | None = None) -> int:
    with client.websocket_connect(url, headers=headers or {}) as ws:
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    return info.value.code


def test_websocket_rejects_missing_session_foreign_job_and_origin(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as owner:
        create_session(owner)
        dataset = prepared_dataset(owner, ROWS)
        job_id = post_job(owner, dataset["id"]).json()["job"]["id"]
        wait_for_terminal(owner, job_id)
        url = f"/api/v1/jobs/{job_id}/stream"

        anonymous = TestClient(app)
        try:
            assert _ws_close_code(anonymous, url) == 4401
        finally:
            anonymous.close()

        assert _ws_close_code(owner, "/api/v1/jobs/job_unknown/stream") == 4404
        assert (
            _ws_close_code(owner, url, headers={"Origin": "http://evil.example"})
            == 4403
        )

        foreign = TestClient(app)
        try:
            create_session(foreign)
            assert _ws_close_code(foreign, url) == 4404
        finally:
            foreign.close()
