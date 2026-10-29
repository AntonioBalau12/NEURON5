"""FastAPI application factory for the NEURON5 offline API."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.graph.reference import preload_reference_graph

from .api import datasets, events, jobs, results, sessions
from .api.errors import install_error_handlers, install_http_middleware
from .api.stores import TERMINAL_STATUSES, ApiState, JobRecord, SessionRecord
from .api.utils import utcnow
from .config import Settings, get_settings

logger = logging.getLogger("neuron5.main")

API_PREFIX = "/api/v1"
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Content-Type", "Idempotency-Key", "X-Requested-With"]


def _remove_file(path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort cleanup
        pass


def _cancel_job(job: JobRecord) -> None:
    task = job.task
    if task is not None and not task.done():
        task.cancel()


def _drop_job(state: ApiState, job: JobRecord) -> None:
    state.jobs.pop(job.id, None)
    state.event_logs.pop(job.id, None)
    for key, job_id in list(state.idempotency.items()):
        if job_id == job.id:
            state.idempotency.pop(key, None)
    _cancel_job(job)
    try:
        shutil.rmtree(job.output_path.parent, ignore_errors=True)
    except OSError:  # pragma: no cover - best effort cleanup
        pass
    dataset = state.datasets.get(job.dataset_id)
    if dataset is not None and not any(
        other.dataset_id == dataset.id for other in state.jobs.values()
    ):
        state.datasets.pop(dataset.id, None)
        _remove_file(dataset.path)
    if state.active_job_id == job.id:
        state.active_job_id = None


def _drop_session(state: ApiState, session: SessionRecord) -> None:
    for job in list(state.jobs.values()):
        if job.session_id == session.id:
            _drop_job(state, job)
    for dataset in list(state.datasets.values()):
        if dataset.session_id == session.id:
            state.datasets.pop(dataset.id, None)
            _remove_file(dataset.path)
    state.sessions.pop(session.id, None)
    state.tokens.pop(session.token, None)


def cleanup_once(state: ApiState) -> None:
    now = utcnow()
    for session in list(state.sessions.values()):
        if session.expires_at <= now:
            _drop_session(state, session)
    grace = max(0, int(state.settings.result_grace_seconds))
    for job in list(state.jobs.values()):
        if job.status not in TERMINAL_STATUSES:
            continue
        terminal_at = job.terminal_at or job.finished_at
        if terminal_at is None:
            continue
        if (now - terminal_at).total_seconds() >= grace:
            _drop_job(state, job)


async def _cleanup_loop(state: ApiState) -> None:
    interval = max(0.05, float(state.settings.cleanup_interval_seconds))
    while True:
        try:
            cleanup_once(state)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - cleanup must keep running
            logger.exception("Cleanup pass failed")
            await asyncio.sleep(interval)


async def _shutdown_jobs(state: ApiState) -> None:
    tasks = [
        job.task
        for job in list(state.jobs.values())
        if job.task is not None and not job.task.done()
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override if settings_override is not None else get_settings()
    state = ApiState.create(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.reference_graph = await asyncio.to_thread(preload_reference_graph)
        state.ensure_dirs()
        cleanup_task = asyncio.create_task(_cleanup_loop(state))
        app.state.cleanup_task = cleanup_task
        try:
            yield
        finally:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)
            await _shutdown_jobs(state)
            await asyncio.to_thread(shutil.rmtree, state.run_dir, True)

    app = FastAPI(
        title="NEURON5 offline classification API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.n5 = state

    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=["X-Request-Id"],
    )
    install_http_middleware(app, settings.cors_origins)

    app.include_router(sessions.router, prefix=API_PREFIX)
    app.include_router(datasets.router, prefix=API_PREFIX)
    app.include_router(jobs.router, prefix=API_PREFIX)
    app.include_router(events.router, prefix=API_PREFIX)
    app.include_router(results.router, prefix=API_PREFIX)
    return app


app = create_app()
