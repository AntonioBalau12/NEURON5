"""Job event history, filtering and the WebSocket stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .errors import ApiError
from .sessions import require_session
from .stores import (
    STAGES,
    TERMINAL_STATUSES,
    ApiState,
    EventRecord,
    JobRecord,
    SessionRecord,
    job_json,
)
from .utils import coerce_int, iso_utc, utcnow

logger = logging.getLogger("neuron5.api.events")

router = APIRouter(tags=["events"])

LEVELS = frozenset({"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"})
TERMINAL_EVENT_TYPES = frozenset({"job.completed", "job.failed"})
PROCESSOR_EVENT_TYPES = frozenset(
    {
        "job.started",
        "step.started",
        "step.completed",
        "progress.updated",
        "row.failed",
        "log.recorded",
    }
)
HEARTBEAT_SECONDS = 15.0
SUBSCRIBER_QUEUE_SIZE = 2048


def get_state(request: Request) -> ApiState:
    return request.app.state.n5


def _owned_job(state: ApiState, session: SessionRecord, job_id: str) -> JobRecord:
    job = state.jobs.get(job_id)
    if job is None or job.session_id != session.id:
        raise ApiError(404, "NOT_FOUND", "Job not found.")
    return job


def _record(
    state: ApiState,
    job: JobRecord,
    *,
    event_type: str,
    level: str,
    component: str,
    step: str | None,
    message: str,
    data: dict[str, Any],
) -> EventRecord:
    log = state.event_log(job.id)
    event = log.append(
        job_id=job.id,
        level=level,
        event_type=event_type,
        component=component,
        step=step,
        message=message,
        data=data,
    )
    log.publish(event)
    return event


def _payload_level(payload: dict[str, Any], default: str) -> str:
    value = payload.get("level")
    if isinstance(value, str) and value.upper() in LEVELS:
        return value.upper()
    return default


def _component(payload: dict[str, Any], default: str = "processor") -> str:
    value = payload.get("component")
    if isinstance(value, str) and value.strip():
        return value
    return default


def _progress_counts(job: JobRecord) -> dict[str, int]:
    return {
        "true": int(job.counts.get("true", 0)),
        "false": int(job.counts.get("false", 0)),
        "unsure": int(job.counts.get("unsure", 0)),
        "fallback": int(job.counts.get("fallback", 0)),
    }


def emit_job_started(state: ApiState, job: JobRecord) -> None:
    log = state.event_log(job.id)
    if log.started_emitted:
        return
    log.started_emitted = True
    _record(
        state,
        job,
        event_type="job.started",
        level="INFO",
        component="orchestrator",
        step=job.stage if job.stage in STAGES else "parse",
        message="Job started.",
        data={},
    )


def ingest_processor_event(
    state: ApiState,
    job: JobRecord,
    event_type: str,
    payload: Any,
) -> None:
    """Called on the event loop for an event emitted by the worker thread."""

    try:
        _ingest_processor_event(state, job, event_type, payload)
    except Exception:  # pragma: no cover - a bad emitter must never kill the job
        logger.exception("Could not ingest processor event %s for job %s", event_type, job.id)


def _ingest_processor_event(
    state: ApiState,
    job: JobRecord,
    event_type: str,
    payload: Any,
) -> None:
    if state.jobs.get(job.id) is not job:
        return
    if job.status in TERMINAL_STATUSES:
        return
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(event_type, str):
        event_type = "log.recorded"
    if event_type in TERMINAL_EVENT_TYPES:
        # Terminal state is controlled by the orchestrator only, after the
        # output file has been validated.
        return

    log = state.event_log(job.id)
    step = payload.get("step") if isinstance(payload.get("step"), str) else None
    level = _payload_level(payload, "INFO")
    message = payload.get("message") if isinstance(payload.get("message"), str) else ""
    data: dict[str, Any] = {}

    if event_type == "job.started":
        if log.started_emitted:
            return
        log.started_emitted = True
        if job.status == "queued":
            job.status = "running"
        if job.started_at is None:
            job.started_at = utcnow()
        step = step or (job.stage if job.stage != "queued" else "parse")
        message = message or "Job started."
    elif event_type == "step.started":
        if step is not None and step in STAGES:
            job.stage = step
            if step in ("write", "validate"):
                job.status = "finalizing"
        message = message or f"Step {step or job.stage} started."
    elif event_type == "step.completed":
        data = {"durationMs": coerce_int(payload.get("durationMs"), 0)}
        message = message or f"Step {step or job.stage} completed."
    elif event_type == "progress.updated":
        processed = max(0, coerce_int(payload.get("processedRows"), job.processed_rows))
        total = job.total_rows
        raw_total = payload.get("totalRows")
        if isinstance(raw_total, int) and not isinstance(raw_total, bool) and raw_total >= 0:
            total = raw_total
        raw_counts = payload.get("counts")
        if isinstance(raw_counts, dict):
            for key in ("true", "false", "unsure", "fallback"):
                if key in raw_counts:
                    job.counts[key] = max(0, coerce_int(raw_counts.get(key), job.counts.get(key, 0)))
        job.processed_rows = processed
        job.total_rows = total
        data = {
            "processedRows": processed,
            "totalRows": total,
            "counts": _progress_counts(job),
        }
        processed_text = str(processed)
        message = message or (
            f"Processed {processed_text} of {total} rows"
            if total is not None
            else f"Processed {processed_text} rows"
        )
        step = step or (job.stage if job.stage != "queued" else None)
    elif event_type == "row.failed":
        job.counts["errors"] = coerce_int(job.counts.get("errors"), 0) + 1
        level = _payload_level(payload, "WARN")
        row_id = payload.get("rowId")
        code = payload.get("code")
        column = payload.get("column")
        data = {
            "rowId": str(row_id) if row_id is not None else "",
            "lineNumber": coerce_int(payload.get("lineNumber"), 0),
            "column": column if isinstance(column, str) else None,
            "code": str(code) if code else "ROW_ERROR",
        }
        message = message or f"Row {data['rowId'] or '?'} failed: {data['code']}."
        step = step or (job.stage if job.stage != "queued" else None)
    elif event_type == "log.recorded":
        data = {}
        step = step or (job.stage if job.stage != "queued" else None)
        message = message or "Log record."
    else:
        data = {"originalType": event_type}
        event_type = "log.recorded"
        step = step or (job.stage if job.stage != "queued" else None)
        message = message or "Log record."

    _record(
        state,
        job,
        event_type=event_type,
        level=level,
        component=_component(payload),
        step=step,
        message=message,
        data=data,
    )


def emit_terminal(
    state: ApiState,
    job: JobRecord,
    *,
    success: bool,
    detail: str | None = None,
) -> None:
    now = utcnow()
    duration = job.duration_seconds
    if duration is None and job.started_at is not None:
        duration = max(0.0, (now - job.started_at).total_seconds())
    if success:
        _record(
            state,
            job,
            event_type="job.completed",
            level="INFO",
            component="orchestrator",
            step="done",
            message=detail or "Job completed successfully.",
            data={
                "totalRows": int(job.total_rows or 0),
                "durationSeconds": round(float(duration or 0.0), 3),
                "counts": dict(job.counts),
            },
        )
    else:
        _record(
            state,
            job,
            event_type="job.failed",
            level="ERROR",
            component="orchestrator",
            step="failed",
            message=detail or f"Job failed: {job.failure_reason or 'PROCESSOR_ERROR'}.",
            data={"failureReason": job.failure_reason},
        )


def _filter_values(request: Request, name: str) -> set[str]:
    values: set[str] = set()
    for raw in request.query_params.getlist(name):
        for part in raw.split(","):
            part = part.strip()
            if part:
                values.add(part.casefold())
    return values


@router.get("/jobs/{job_id}/events")
async def list_events(
    request: Request,
    job_id: str,
    afterSequenceId: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    job = _owned_job(state, session, job_id)
    log = state.event_log(job.id)
    levels = _filter_values(request, "level")
    components = _filter_values(request, "component")
    types = _filter_values(request, "type")
    matching: list[EventRecord] = []
    for event in log.events:
        if event.sequence_id <= afterSequenceId:
            continue
        if levels and event.level.casefold() not in levels:
            continue
        if components and event.component.casefold() not in components:
            continue
        if types and event.event_type.casefold() not in types:
            continue
        matching.append(event)
    selected = matching[:limit]
    return {
        "events": [event.to_json() for event in selected],
        "lastSequenceId": log.last_sequence,
        "truncated": log.truncated_for(afterSequenceId),
        "total": len(matching),
    }


async def _reject(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.accept()
        await websocket.close(code=code, reason=reason)
    except Exception:  # pragma: no cover - client may vanish mid-handshake
        pass


@router.websocket("/jobs/{job_id}/stream")
async def stream_job_events(
    websocket: WebSocket,
    job_id: str,
    lastSequenceId: int = 0,
) -> None:
    state: ApiState = websocket.app.state.n5
    settings = state.settings
    session = state.session_for_token(websocket.cookies.get(settings.cookie_name))
    if session is None:
        await _reject(websocket, 4401, "SESSION_REQUIRED")
        return
    job = state.jobs.get(job_id)
    if job is None or job.session_id != session.id:
        await _reject(websocket, 4404, "NOT_FOUND")
        return
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        await _reject(websocket, 4403, "INVALID_ORIGIN")
        return

    await websocket.accept()
    log = state.event_log(job.id)
    queue: asyncio.Queue[EventRecord] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    log.subscribers.add(queue)
    try:
        replay_upto = log.last_sequence
        requested = min(max(0, int(lastSequenceId)), replay_upto)
        terminal_at_connect = job.status in TERMINAL_STATUSES
        gap, replay_from = log.gap_for(requested)
        snapshot = job_json(job)
        replayed = [event for event in log.events_after(requested) if event.sequence_id <= replay_upto]
        last_sent = replay_upto
        await websocket.send_json(
            {
                "kind": "handshake",
                "protocolVersion": 1,
                "jobId": job.id,
                "status": job.status,
                "lastSequenceId": replay_upto,
                "replayAvailable": not gap,
                "serverTime": iso_utc(utcnow()),
            }
        )
        await websocket.send_json(
            {
                "kind": "snapshot",
                "job": snapshot,
                "gap": gap,
                "replayFrom": replay_from,
            }
        )
        for event in replayed:
            await websocket.send_json({"kind": "event", "event": event.to_json()})
        if terminal_at_connect:
            await asyncio.sleep(0.05)
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                if job.status in TERMINAL_STATUSES and log.last_sequence <= last_sent:
                    break
                await websocket.send_json(
                    {"kind": "heartbeat", "serverTime": iso_utc(utcnow())}
                )
                continue
            if event.sequence_id <= last_sent:
                continue
            await websocket.send_json({"kind": "event", "event": event.to_json()})
            last_sent = event.sequence_id
            if event.event_type in TERMINAL_EVENT_TYPES:
                await asyncio.sleep(0.05)
                break
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError):
        pass
    finally:
        log.subscribers.discard(queue)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:  # pragma: no cover - already gone
                pass
