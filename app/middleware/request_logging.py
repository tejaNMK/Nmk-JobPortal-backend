from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.context import reset_request_id, set_request_id
from app.observability.logging import redact_sensitive_data


REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"
DEFAULT_EXCLUDED_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}

logger = logging.getLogger("app.request")


def _is_valid_request_id(value: str | None) -> bool:
    if not value:
        return False

    stripped = value.strip()
    if not 1 <= len(stripped) <= 128:
        return False

    return all(char.isprintable() and char not in "\r\n\t" for char in stripped)


def _request_id_from_headers(request: Request) -> str:
    incoming_request_id = request.headers.get(REQUEST_ID_HEADER)
    incoming_correlation_id = request.headers.get(CORRELATION_ID_HEADER)

    for candidate in (incoming_request_id, incoming_correlation_id):
        if _is_valid_request_id(candidate):
            return candidate.strip()

    return str(uuid.uuid4())


def _route_path(request: Request) -> str | None:
    route = request.scope.get("route")
    return getattr(route, "path", None)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        excluded_paths: Iterable[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.excluded_paths = set(excluded_paths or DEFAULT_EXCLUDED_PATHS)

    async def dispatch(self, request: Request, call_next):
        request_id = _request_id_from_headers(request)
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            if request.url.path not in self.excluded_paths:
                logger.info(
                    "HTTP request completed",
                    extra=redact_sensitive_data(
                        {
                            "event": "http_request_completed",
                            "http_method": request.method,
                            "path": request.url.path,
                            "route": _route_path(request),
                            "status_code": status_code,
                            "duration_ms": duration_ms,
                            "client_host": (
                                request.client.host if request.client else None
                            ),
                        }
                    ),
                )
            reset_request_id(token)
