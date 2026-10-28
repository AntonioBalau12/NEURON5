"""Job orchestration: ownership, idempotency, deadline and the state machine."""

from __future__ import annotations

import asyncio
import csv
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..engine.api import (
    Engine,
    MappingSpec,
    ProcessOutcome,
    create_engine,
    process_csv,
)
from .errors import ApiError
from .events import emit_job_started, emit_terminal, ingest_processor_event
from .sessions import require_session
from .stores import (
    TERMINAL_STATUSES,
    ApiState,
    DatasetRecord,
    JobRecord,
    SessionRecord,
    job_json,
)
from .utils import new_id, normalize_counts, utcnow

logger = logging.getLogger("neuron5.api.jobs")

router = APIRouter(tags=["jobs"])

#: Module-level seam used by the API tests (and by alternative deployments) to
#: build the classifier.  Production uses the frozen engine factory.
engine_factory: Callable[..., Engine] = create_engine


def get_state(request: Request) -> ApiState:
    return request.app.state.n5


def _extract_idempotency_key(request: Request) -> str | None:
    raw = request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    if (
        not raw
        or len(raw) > 128
        or any(ord(character) < 32 or ord(character) > 126 for character in raw)
    ):
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "Idempotency-Key must contain 1 to 128 printable characters.",
            {"maxLength": 128},
        )
    return raw


def _arena_deadline() -> float | None:
    raw = os.environ.get("ARENA_DEADLINE")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _mapping_spec(dataset: DatasetRecord) -> MappingSpec:
    mapping = dataset.mapping or {}
    return MappingSpec(
        text_column=str(mapping.get("textColumn")),
        date_column=mapping.get("dateColumn") or None,
        id_column=mapping.get("idColumn") or None,
        result_column=str(mapping.get("resultColumn") or "label"),
    )


def _verify_output(job: JobRecord) -> bool:
    """Validate the output against the binding contract section 7.

    The output CSV must contain the input columns in the same order plus the
    result column, with exactly the input row count.  A violation is a failed
    job (INVALID_OUTPUT); it must never be downgraded to a warning, otherwise
    the API would advertise success for an incomplete result.
    """
    outcome = job.outcome
    if outcome is None or not outcome.valid:
        return False
    path = job.output_path
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                return False
            # Exactly the input columns in order, with the result column
            # overwritten in place or appended when it did not exist.
            if not header or header != list(job.expected_columns):
                return False
            count = sum(1 for row in reader if row)
    except (OSError, UnicodeError, csv.Error):
        return False
    if outcome.total_rows is None or int(outcome.total_rows) != count:
        return False
    if job.expected_rows is not None and int(job.expected_rows) != count:
        return False
    return True


def _finalize_failure(
    state: ApiState,
    job: JobRecord,
    reason: str,
    detail: str,
) -> None:
    now = utcnow()
    job.status = "failed"
    job.stage = "failed"
    job.failure_reason = reason
    job.result_available = False
    job.finished_at = now
    job.terminal_at = now
    if job.started_at is None:
        job.started_at = now
    emit_terminal(state, job, success=False, detail=detail)


async def _apply_outcome(state: ApiState, job: JobRecord, outcome: ProcessOutcome) -> None:
    job.outcome = outcome
    job.status = "finalizing"
    job.stage = "validate"
    job.duration_seconds = float(outcome.duration_seconds or 0.0)
    job.total_rows = int(outcome.total_rows)
    job.processed_rows = max(0, int(outcome.processed_rows))
    job.counts = normalize_counts(outcome.counts, len(outcome.errors))
    try:
        valid = await asyncio.to_thread(_verify_output, job)
    except Exception:  # pragma: no cover - verification must never escape
        logger.exception("Could not verify output for job %s", job.id)
        valid = False
    now = utcnow()
    job.finished_at = now
    job.terminal_at = now
    if valid:
        job.status = "succeeded"
        job.stage = "done"
        job.result_available = True
        job.failure_reason = None
        if outcome.timed_out and "TIMED_OUT_FALLBACK" not in job.warnings:
            job.warnings.append("TIMED_OUT_FALLBACK")
        emit_terminal(state, job, success=True)
    else:
        job.status = "failed"
        job.stage = "failed"
        job.result_available = False
        job.failure_reason = "INVALID_OUTPUT"
        emit_terminal(
            state,
            job,
            success=False,
            detail="The output CSV was incomplete or failed validation.",
        )


async def run_job(state: ApiState, job: JobRecord) -> None:
    """Process one job off the event loop, then publish the terminal event."""

    try:
        job.status = "running"
        job.started_at = utcnow()
        if job.stage == "queued":
            job.stage = "parse"
        emit_job_started(state, job)
        loop = asyncio.get_running_loop()

        def emitter(event_type: str, payload: dict[str, Any]) -> None:
            try:
                loop.call_soon_threadsafe(
                    ingest_processor_event, state, job, event_type, payload
                )
            except RuntimeError:  # pragma: no cover - loop shutting down
                pass

        def work() -> ProcessOutcome:
            engine = engine_factory(state.settings.data_dir, settings=state.settings)
            try:
                return process_csv(
                    job.input_path,
                    job.output_path,
                    job.mapping,
                    engine,
                    deadline_epoch=job.deadline_epoch,
                    emit=emitter,
                    progress_every=job.progress_every,
                    as_of=job.as_of,
                )
            finally:
                try:
                    engine.close()
                except Exception:  # pragma: no cover - engine cleanup is best effort
                    logger.exception("Engine close failed for job %s", job.id)

        try:
            outcome = await asyncio.to_thread(work)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Classifier-service failures are infrastructure errors, distinct
            # from a processor bug.  Match by class name so the API keeps its
            # dependency on the frozen engine seam only, not on remote_engine.
            failure_name = type(exc).__name__
            if failure_name == "ClassifierUnavailable":
                logger.warning("Classifier unavailable for job %s: %s", job.id, exc)
                _finalize_failure(
                    state,
                    job,
                    "CLASSIFIER_UNAVAILABLE",
                    "The classification service is unavailable.",
                )
            elif failure_name == "ClassifierTimeout":
                logger.warning("Classifier timed out for job %s: %s", job.id, exc)
                _finalize_failure(
                    state,
                    job,
                    "TIMEOUT",
                    "The classification service did not answer in time.",
                )
            else:
                logger.exception("Processor failed for job %s", job.id)
                _finalize_failure(
                    state,
                    job,
                    "PROCESSOR_ERROR",
                    "The processor failed unexpectedly.",
                )
        else:
            if not isinstance(outcome, ProcessOutcome):
                logger.error("Processor returned %r for job %s", type(outcome), job.id)
                _finalize_failure(
                    state,
                    job,
                    "PROCESSOR_ERROR",
                    "The processor returned an invalid outcome.",
                )
            else:
                try:
                    await _apply_outcome(state, job, outcome)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("Could not finalize job %s", job.id)
                    if job.status not in TERMINAL_STATUSES:
                        _finalize_failure(
                            state,
                            job,
                            "PROCESSOR_ERROR",
                            "The job could not be finalized.",
                        )
    finally:
        if state.active_job_id == job.id:
            state.active_job_id = None


@router.post("/jobs", status_code=202)
async def create_job(
    request: Request,
    session: SessionRecord = Depends(require_session),
) -> JSONResponse:
    state = get_state(request)
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "INVALID_REQUEST", "Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_REQUEST", "Request body must be a JSON object.")
    dataset_id = body.get("datasetId")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ApiError(400, "INVALID_REQUEST", "datasetId is required.")
    dataset = state.datasets.get(dataset_id)
    if dataset is None or dataset.session_id != session.id:
        raise ApiError(404, "NOT_FOUND", "Dataset not found.")
    mapping = dataset.mapping
    if not mapping or not mapping.get("confirmed"):
        raise ApiError(
            409,
            "MAPPING_REQUIRED",
            "The dataset mapping must be confirmed before starting a job.",
            {"datasetId": dataset.id},
        )
    idempotency_key = _extract_idempotency_key(request)
    if idempotency_key is not None:
        existing_id = state.idempotency.get((session.id, idempotency_key))
        if existing_id is not None:
            existing = state.jobs.get(existing_id)
            if existing is not None:
                if existing.dataset_id != dataset_id:
                    raise ApiError(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This Idempotency-Key was already used with a different dataset.",
                        {"idempotencyKey": idempotency_key},
                    )
                return JSONResponse(
                    {
                        "job": {"id": existing.id, "status": existing.status},
                        "replayed": True,
                    },
                    status_code=200,
                )
            state.idempotency.pop((session.id, idempotency_key), None)
    active = state.active_job()
    if active is not None:
        raise ApiError(
            409,
            "JOB_ALREADY_RUNNING",
            "Another job is already running.",
            {"activeJobId": active.id},
        )

    now = utcnow()
    settings = state.settings
    deadline_epoch = now.timestamp() + float(settings.job_deadline_seconds)
    arena_deadline = _arena_deadline()
    if arena_deadline is not None:
        deadline_epoch = min(deadline_epoch, arena_deadline)
    deadline_at = datetime.fromtimestamp(deadline_epoch, tz=timezone.utc)
    job_id = new_id("job")
    state.ensure_dirs()
    output_path = state.job_output_path(job_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_spec = _mapping_spec(dataset)
    expected_columns = list(dataset.columns)
    if mapping_spec.result_column not in expected_columns:
        expected_columns.append(mapping_spec.result_column)
    job = JobRecord(
        id=job_id,
        dataset_id=dataset.id,
        session_id=session.id,
        created_at=now,
        deadline_at=deadline_at,
        deadline_epoch=deadline_epoch,
        input_path=dataset.path,
        output_path=output_path,
        mapping=mapping_spec,
        expected_rows=dataset.row_count,
        expected_columns=expected_columns,
        progress_every=int(settings.progress_every_rows),
        as_of=settings.as_of_date or None,
        total_rows=dataset.row_count,
    )
    state.jobs[job.id] = job
    state.active_job_id = job.id
    dataset.mapping_frozen = True
    if idempotency_key is not None:
        state.idempotency[(session.id, idempotency_key)] = job.id
    try:
        job.task = asyncio.create_task(run_job(state, job))
    except Exception:  # pragma: no cover - create_task only fails without a loop
        state.jobs.pop(job.id, None)
        state.active_job_id = None
        raise ApiError(500, "INTERNAL_ERROR", "Could not start the job.")
    return JSONResponse(
        {"job": {"id": job.id, "status": "queued"}, "replayed": False},
        status_code=202,
    )


@router.get("/jobs/{job_id}")
async def get_job(
    request: Request,
    job_id: str,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    job = state.owned_job(session, job_id)
    return job_json(job)
