import logging
from http import HTTPStatus
from typing import Any, Dict, Iterable, List

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schema.common import FieldError, ResponseSchema, error_response


logger = logging.getLogger(__name__)


ERROR_CODES: Dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    412: "PRECONDITION_FAILED",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_SERVER_ERROR",
    501: "NOT_IMPLEMENTED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def _response_content(response: ResponseSchema[Any]) -> Dict[str, Any]:
    return jsonable_encoder(response, exclude_none=True)


def _default_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _http_error_parts(status_code: int, detail: Any) -> tuple[str, str, str]:
    default_code = ERROR_CODES.get(status_code, "HTTP_ERROR")

    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or _default_message(status_code))
        code = str(detail.get("code") or default_code)
        details = str(detail.get("details") or detail.get("detail") or message)
        return message, code, details

    message = str(detail or _default_message(status_code))
    return message, default_code, message


def _format_validation_errors(errors: Iterable[Dict[str, Any]]) -> str:
    formatted = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = str(error.get("msg", "Invalid value"))
        formatted.append(f"{location}: {message}" if location else message)
    return "; ".join(formatted) or "Request validation failed"


def _extract_field_errors(errors: Iterable[Dict[str, Any]]) -> List[FieldError]:
    """Extract per-field validation errors from Pydantic error list."""
    field_errors = []
    for error in errors:
        loc = error.get("loc", ())
        # Skip non-field locations (like "body" without a field name)
        # The last element of loc is typically the field name
        field_name = None
        for part in reversed(loc):
            if isinstance(part, str) and part not in ("body", "query", "path", "header", "cookie"):
                field_name = part
                break
        message = str(error.get("msg", "Invalid value"))
        if field_name:
            field_errors.append(FieldError(field=field_name, message=message))
    return field_errors


def _request_log_context(request: Request) -> Dict[str, Any]:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "http_method": request.method,
        "path": request.url.path,
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register standard handlers for application and framework errors."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info(
            "Request validation failed",
            extra={
                "event": "request_validation_failed",
                "status_code": 422,
                **_request_log_context(request),
            },
        )
        details = _format_validation_errors(exc.errors())
        field_errors = _extract_field_errors(exc.errors())
        response = error_response(
            status=422,
            message="Request validation failed",
            code="VALIDATION_ERROR",
            details=details,
            fields=field_errors,
        )
        return JSONResponse(status_code=422, content=_response_content(response))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "HTTP exception raised",
                exc_info=(type(exc), exc, exc.__traceback__),
                extra={
                    "event": "http_exception",
                    "status_code": exc.status_code,
                    **_request_log_context(request),
                },
            )
        message, code, details = _http_error_parts(exc.status_code, exc.detail)
        response = error_response(
            status=exc.status_code,
            message=message,
            code=code,
            details=details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_response_content(response),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled API exception",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={
                "event": "unhandled_api_exception",
                "status_code": 500,
                **_request_log_context(request),
            },
        )
        response = error_response(
            status=500,
            message="Internal server error",
            code="INTERNAL_SERVER_ERROR",
            details="An unexpected error occurred while processing the request.",
        )
        return JSONResponse(status_code=500, content=_response_content(response))
