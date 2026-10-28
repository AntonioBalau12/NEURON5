"""Stable error envelope and exception handling for the API.

Every error a client can observe is rendered as::

    {"error": {"code": "...", "message": "...", "details": {...}},
     "requestId": "req_..."}

The contract in backend/docs/API_CONTRACT.md fixes the codes and statuses;
this module is the single place that renders them.
"""

from __future__ import annotations

import logging
import secrets
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("neuron5.api")

REQUEST_ID_HEADER = "X-Request-Id"
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_REQUEST_ID: ContextVar[str | None] = ContextVar("n5_request_id", default=None)


class ApiError(Exception):
    """An error that maps directly onto the public error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def new_request_id() -> str:
    return "req_" + secrets.token_hex(8)


def set_request_id(request_id: str):
    return _REQUEST_ID.set(request_id)


def reset_request_id(token) -> None:
    _REQUEST_ID.reset(token)


def current_request_id(request: Request | None = None) -> str:
    if request is not None:
        value = getattr(request.state, "request_id", None)
        if value:
            return str(value)
    value = _REQUEST_ID.get()
    return value or new_request_id()


def error_response(
    request: Request | None,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = current_request_id(request)
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    body["requestId"] = request_id
    return JSONResponse(
        body,
        status_code=status_code,
        headers={REQUEST_ID_HEADER: request_id},
    )


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for error in errors:
        cleaned.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return cleaned


def _http_error_code(status_code: int) -> str:
    if status_code == 401:
        return "SESSION_REQUIRED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 413:
        return "PAYLOAD_TOO_LARGE"
    if status_code == 415:
        return "UNSUPPORTED_MEDIA_TYPE"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "INVALID_REQUEST"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            400,
            "INVALID_REQUEST",
            "Request validation failed.",
            {"errors": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = int(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else "Request failed."
        return error_response(request, status, _http_error_code(status), message)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API exception on %s %s", request.method, request.url.path)
        return error_response(
            request,
            500,
            "INTERNAL_ERROR",
            "An internal server error occurred.",
        )


def install_http_middleware(app: FastAPI, allowed_origins: tuple[str, ...]) -> None:
    """Install the request-id middleware and the Origin (CSRF) guard.

    The middleware is installed last, which in Starlette makes it the
    outermost user middleware: every response -- including errors and CORS
    responses -- carries X-Request-Id.  State-changing requests with a
    foreign Origin are rejected before they reach a route.  Requests without
    an Origin header (curl, tests) are allowed, exactly as the contract
    requires.
    """

    origins = frozenset(allowed_origins)

    @app.middleware("http")
    async def _request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = new_request_id()
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            origin = request.headers.get("origin")
            if (
                request.method in STATE_CHANGING_METHODS
                and origin is not None
                and origin not in origins
            ):
                return error_response(
                    request,
                    403,
                    "INVALID_REQUEST",
                    "The request Origin is not allowed.",
                )
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
