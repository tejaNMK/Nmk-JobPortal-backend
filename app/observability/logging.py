from __future__ import annotations

import json
import logging
import os
import socket
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import LogRecord
from typing import Any

from app.observability.context import get_request_id


REDACTED = "[REDACTED]"
DEFAULT_SERVICE_NAME = "nmk-jobportal-userservice"

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set_cookie",
    "password",
    "current_password",
    "new_password",
    "confirm_password",
    "otp",
    "otp_code",
    "token",
    "access_token",
    "refresh_token",
    "jwt",
    "secret",
    "client_secret",
    "api_key",
    "smtp_password",
    "aws_access_key_id",
    "aws_secret_access_key",
    "database_url",
}

RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


@dataclass(frozen=True)
class LoggingSettings:
    service_name: str
    environment: str
    log_level: str
    json_logs: bool
    cloudwatch_enabled: bool
    cloudwatch_log_group: str | None
    cloudwatch_log_stream: str | None
    cloudwatch_retention_days: int | None
    aws_region: str | None


def get_logging_settings() -> LoggingSettings:
    return LoggingSettings(
        service_name=os.getenv("SERVICE_NAME", DEFAULT_SERVICE_NAME).strip()
        or DEFAULT_SERVICE_NAME,
        environment=os.getenv(
            "LOG_ENVIRONMENT",
            os.getenv("APP_ENV", "development"),
        ).strip()
        or "development",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        json_logs=os.getenv("LOG_FORMAT", "json").strip().lower() == "json",
        cloudwatch_enabled=_get_bool_env("CLOUDWATCH_LOGGING_ENABLED", False),
        cloudwatch_log_group=_get_optional_env("CLOUDWATCH_LOG_GROUP"),
        cloudwatch_log_stream=_get_optional_env("CLOUDWATCH_LOG_STREAM"),
        cloudwatch_retention_days=_get_optional_int_env(
            "CLOUDWATCH_LOG_RETENTION_DAYS"
        ),
        aws_region=_get_optional_env("AWS_REGION"),
    )


def _get_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_optional_int_env(name: str) -> int | None:
    value = _get_optional_env(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in SENSITIVE_KEYS:
        return True

    return any(
        marker in normalized
        for marker in (
            "authorization",
            "cookie",
            "password",
            "otp",
            "token",
            "secret",
            "api_key",
        )
    )


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_sensitive_data(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)

    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or get_request_id()
        return True


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def formatTime(self, record: LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key in RESERVED_LOG_RECORD_FIELDS or key == "request_id":
                continue
            if key.startswith("_"):
                continue
            payload[key] = redact_sensitive_data(value)

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "stacktrace": "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                ),
            }

        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(
            redact_sensitive_data(payload),
            default=str,
            ensure_ascii=False,
        )


class SafeDelegatingHandler(logging.Handler):
    def __init__(self, target: logging.Handler) -> None:
        super().__init__(target.level)
        self.target = target

    def emit(self, record: LogRecord) -> None:
        try:
            self.target.handle(record)
        except Exception:
            return

    def flush(self) -> None:
        try:
            self.target.flush()
        except Exception:
            return

    def close(self) -> None:
        try:
            self.target.close()
        finally:
            super().close()


def _coerce_log_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def _default_cloudwatch_log_group(settings: LoggingSettings) -> str:
    return f"/{settings.environment}/{settings.service_name}"


def _default_cloudwatch_log_stream(settings: LoggingSettings) -> str:
    hostname = socket.gethostname() or "unknown-host"
    return f"{settings.environment}/{settings.service_name}/{hostname}/{os.getpid()}"


def _build_cloudwatch_handler(
    settings: LoggingSettings,
    *,
    level: int,
    formatter: logging.Formatter,
) -> logging.Handler | None:
    if not settings.cloudwatch_enabled:
        return None

    try:
        import boto3
        import watchtower
    except ImportError as exc:
        logging.getLogger(__name__).warning(
            "CloudWatch logging disabled because dependency is missing",
            extra={
                "event": "cloudwatch_logging_dependency_missing",
                "missing_dependency": exc.name,
            },
        )
        return None

    try:
        session = boto3.Session(region_name=settings.aws_region)
        logs_client = session.client("logs")
        handler = watchtower.CloudWatchLogHandler(
            boto3_client=logs_client,
            log_group_name=(
                settings.cloudwatch_log_group
                or _default_cloudwatch_log_group(settings)
            ),
            log_stream_name=(
                settings.cloudwatch_log_stream
                or _default_cloudwatch_log_stream(settings)
            ),
            create_log_group=True,
            create_log_stream=True,
            log_group_retention_days=settings.cloudwatch_retention_days,
            use_queues=True,
        )
        handler.setLevel(level)
        handler.setFormatter(formatter)
        handler.addFilter(RequestContextFilter())
        return SafeDelegatingHandler(handler)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "CloudWatch logging disabled because handler initialization failed",
            extra={
                "event": "cloudwatch_logging_initialization_failed",
                "error_type": exc.__class__.__name__,
            },
        )
        return None


def configure_logging(settings: LoggingSettings | None = None) -> None:
    settings = settings or get_logging_settings()
    level = _coerce_log_level(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(RequestContextFilter())

    if settings.json_logs:
        formatter = JsonLogFormatter(
            service_name=settings.service_name,
            environment=settings.environment,
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] "
            "[request_id=%(request_id)s] %(message)s"
        )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    cloudwatch_handler = _build_cloudwatch_handler(
        settings,
        level=level,
        formatter=formatter,
    )
    if cloudwatch_handler:
        root_logger.addHandler(cloudwatch_handler)

    logging.captureWarnings(True)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    for noisy_logger in ("botocore", "boto3", "urllib3", "asyncio"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
