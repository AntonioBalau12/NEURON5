"""Result summary, preview, errors and the streamed CSV download."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .errors import ApiError
from .sessions import require_session
from .stores import (
    TERMINAL_STATUSES,
    ApiState,
    JobRecord,
    SessionRecord,
    job_json,
)
from .utils import (
    iter_file_chunks,
    normalize_counts,
    parse_pagination,
    read_csv_page,
)

router = APIRouter(tags=["results"])

RESULT_CONTENT_TYPE = "text/csv; charset=utf-8"


def get_state(request: Request) -> ApiState:
    return request.app.state.n5


def _owned_job(state: ApiState, session: SessionRecord, job_id: str) -> JobRecord:
    job = state.jobs.get(job_id)
    if job is None or job.session_id != session.id:
        raise ApiError(404, "NOT_FOUND", "Job not found.")
    return job


def _require_terminal(job: JobRecord) -> None:
    if job.status not in TERMINAL_STATUSES:
        raise ApiError(
            409,
            "JOB_NOT_READY",
            "The job has not finished yet.",
            {"status": job.status},
        )


def _result_ready(job: JobRecord) -> bool:
    if not job.result_available or job.outcome is None or not job.outcome.valid:
        return False
    try:
        return job.output_path.is_file()
    except OSError:  # pragma: no cover - defensive
        return False


def _require_result(job: JobRecord) -> None:
    _require_terminal(job)
    if not _result_ready(job):
        raise ApiError(
            409,
            "JOB_NOT_READY",
            "The job result is not ready.",
            {"status": job.status, "resultAvailable": bool(job.result_available)},
        )


def _normalized_errors(job: JobRecord) -> list[dict[str, Any]]:
    if job.outcome is None:
        return []
    result: list[dict[str, Any]] = []
    for error in job.outcome.errors:
        if not isinstance(error, dict):
            continue
        column = error.get("column")
        result.append(
            {
                "rowId": str(error.get("rowId") or ""),
                "lineNumber": int(error.get("lineNumber") or 0),
                "column": column if isinstance(column, str) else None,
                "code": str(error.get("code") or "ROW_ERROR"),
                "message": str(error.get("message") or ""),
            }
        )
    return result


def _duration_seconds(job: JobRecord) -> float:
    value: float | None = job.duration_seconds
    if value is None and job.outcome is not None:
        value = float(job.outcome.duration_seconds)
    if value is None and job.started_at is not None:
        finished = job.finished_at or job.started_at
        value = max(0.0, (finished - job.started_at).total_seconds())
    return round(float(value or 0.0), 3)


def _summary_counts(job: JobRecord, errors_count: int) -> dict[str, int]:
    if job.outcome is not None:
        return normalize_counts(job.outcome.counts, errors_count)
    return normalize_counts(job.counts, errors_count)


@router.get("/jobs/{job_id}/result/summary")
async def result_summary(
    request: Request,
    job_id: str,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    job = _owned_job(state, session, job_id)
    _require_terminal(job)
    errors = _normalized_errors(job)
    ready = _result_ready(job)
    output: dict[str, Any] | None = None
    if ready:
        try:
            byte_size = job.output_path.stat().st_size
        except OSError:  # pragma: no cover - defensive
            byte_size = 0
        output = {
            "fileName": "result.csv",
            "bytes": int(byte_size),
            "contentType": RESULT_CONTENT_TYPE,
        }
    total_rows = (
        int(job.outcome.total_rows)
        if job.outcome is not None
        else int(job.total_rows or 0)
    )
    return {
        "jobId": job.id,
        "status": job.status,
        "totalRows": total_rows,
        "counts": _summary_counts(job, len(errors)),
        "durationSeconds": _duration_seconds(job),
        "warnings": list(job.warnings),
        "failureReason": job.failure_reason,
        "output": output,
        "errorsCount": len(errors),
    }


@router.get("/jobs/{job_id}/result/preview")
async def result_preview(
    request: Request,
    job_id: str,
    offset: int = 0,
    limit: int | None = None,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    job = _owned_job(state, session, job_id)
    _require_result(job)
    resolved_offset, resolved_limit = parse_pagination(offset, limit, state.settings)
    assert job.outcome is not None
    try:
        columns, rows, total = await asyncio.to_thread(
            read_csv_page,
            job.output_path,
            ",",
            resolved_offset,
            resolved_limit,
            int(job.outcome.total_rows),
        )
    except ApiError as exc:
        raise ApiError(
            409,
            "JOB_NOT_READY",
            "The job result is not ready.",
            {"status": job.status},
        ) from exc
    return {
        "columns": columns,
        "rows": rows,
        "offset": resolved_offset,
        "limit": resolved_limit,
        "total": total,
    }


@router.get("/jobs/{job_id}/result/errors")
async def result_errors(
    request: Request,
    job_id: str,
    offset: int = 0,
    limit: int | None = None,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    job = _owned_job(state, session, job_id)
    _require_terminal(job)
    resolved_offset, resolved_limit = parse_pagination(offset, limit, state.settings)
    errors = _normalized_errors(job)
    page = errors[resolved_offset : resolved_offset + resolved_limit]
    return {
        "items": page,
        "offset": resolved_offset,
        "limit": resolved_limit,
        "total": len(errors),
    }


@router.get("/jobs/{job_id}/result.csv")
async def result_csv(
    request: Request,
    job_id: str,
    session: SessionRecord = Depends(require_session),
) -> StreamingResponse:
    state = get_state(request)
    job = _owned_job(state, session, job_id)
    _require_result(job)
    return StreamingResponse(
        iter_file_chunks(job.output_path),
        media_type=RESULT_CONTENT_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="result-{job.id}.csv"'
        },
    )
