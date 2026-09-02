import logging
from collections.abc import Mapping
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import SentrySettings, get_sentry_settings


logger = logging.getLogger(__name__)
REDACTED = "[Filtered]"

SENSITIVE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "confirm_password",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "secret",
    "client_secret",
    "smtp_password",
    "aws_secret_access_key",
    "database_url",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in {item.replace("-", "_") for item in SENSITIVE_KEYS}:
        return True

    return any(
        marker in normalized
        for marker in (
            "password",
            "otp",
            "token",
            "secret",
            "api_key",
            "authorization",
            "cookie",
        )
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(key) else _sanitize(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_sanitize(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)

    return value


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    return _sanitize(event)


def initialize_sentry(settings: SentrySettings | None = None) -> bool:
    settings = settings or get_sentry_settings()

    if not settings.dsn:
        logger.info("Sentry error tracking is disabled because SENTRY_DSN is not configured.")
        return False

    sentry_sdk.init(
        dsn=settings.dsn,
        environment=settings.environment,
        release=settings.release,
        traces_sample_rate=settings.traces_sample_rate,
        integrations=[
            StarletteIntegration(failed_request_status_codes=set(range(500, 600))),
            FastApiIntegration(failed_request_status_codes=set(range(500, 600))),
        ],
        send_default_pii=False,
        before_send=before_send,
    )
    logger.info("Sentry error tracking initialized.")
    return True
