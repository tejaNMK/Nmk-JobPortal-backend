import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_logging import RequestLoggingMiddleware
from app.observability.context import get_request_id
from app.observability.logging import JsonLogFormatter


def test_request_logging_middleware_propagates_request_id():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, excluded_paths=[])

    @app.get("/ping")
    async def ping():
        return {"request_id": get_request_id()}

    response = TestClient(app).get(
        "/ping",
        headers={"X-Request-ID": "req-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"
    assert response.json() == {"request_id": "req-123"}


def test_json_log_formatter_redacts_sensitive_extra_fields():
    formatter = JsonLogFormatter(
        service_name="userservice",
        environment="test",
    )
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="created",
        args=(),
        exc_info=None,
    )
    record.password = "secret"
    record.headers = {
        "Authorization": "Bearer token",
        "X-Request-ID": "req-123",
    }

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "created"
    assert payload["service"] == "userservice"
    assert payload["password"] == "[REDACTED]"
    assert payload["headers"]["Authorization"] == "[REDACTED]"
    assert payload["headers"]["X-Request-ID"] == "req-123"
