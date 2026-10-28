"""Anonymous session creation and the session dependency."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .errors import ApiError
from .stores import ApiState, SessionRecord, session_json
from .utils import new_id, utcnow

router = APIRouter(tags=["sessions"])


def get_state(request: Request) -> ApiState:
    return request.app.state.n5


def _set_session_cookie(response: JSONResponse, settings, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=int(settings.session_ttl_seconds),
        path="/",
        httponly=True,
        samesite="lax",
        secure=False,
    )


@router.post("/sessions")
async def create_session(request: Request) -> JSONResponse:
    state = get_state(request)
    now = utcnow()
    existing = state.session_for_token(request.cookies.get(state.settings.cookie_name))
    if existing is not None:
        existing.expires_at = now + timedelta(seconds=state.settings.session_ttl_seconds)
        session = existing
    else:
        token = secrets.token_urlsafe(32)
        session = SessionRecord(
            id=new_id("sess"),
            token=token,
            created_at=now,
            expires_at=now + timedelta(seconds=state.settings.session_ttl_seconds),
        )
        state.sessions[session.id] = session
        state.tokens[token] = session.id
    response = JSONResponse(session_json(session))
    _set_session_cookie(response, state.settings, session.token)
    return response


async def require_session(request: Request) -> SessionRecord:
    state = get_state(request)
    session = state.session_for_token(request.cookies.get(state.settings.cookie_name))
    if session is None:
        raise ApiError(
            401,
            "SESSION_REQUIRED",
            "A valid session is required.",
        )
    return session


@router.get("/sessions/current")
async def current_session(session: SessionRecord = Depends(require_session)) -> dict:
    return session_json(session)
