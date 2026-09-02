from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


# =========================
# LOAD ENVIRONMENT VARIABLES
# =========================
load_dotenv()


# =========================
# DATABASE CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required"
    )


# =========================
# CORS
# =========================
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
PRODUCTION_ENVS = {"production", "prod"}
DEVELOPMENT_ENVS = {"development", "dev", "local", "test", "testing"}
DEV_DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
LOCALHOST_NAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"{name} must be a boolean value")


def _get_int_env(
    name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer value") from exc

    if parsed < minimum:
        raise RuntimeError(f"{name} must be greater than or equal to {minimum}")

    return parsed


def _split_origins(value: str | None) -> list[str]:
    if value is None:
        return []

    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def _is_localhost_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    hostname = parsed.hostname or ""
    return hostname in LOCALHOST_NAMES or hostname.endswith(".localhost")


def validate_cors_origins(
    origins: list[str],
    *,
    app_env: str,
    allow_credentials: bool,
) -> list[str]:
    normalized_env = app_env.strip().lower()

    if not origins:
        raise RuntimeError("CORS_ALLOWED_ORIGINS must include at least one trusted origin")

    validated: list[str] = []
    seen: set[str] = set()

    for origin in origins:
        if origin == "*":
            raise RuntimeError("CORS_ALLOWED_ORIGINS must not contain wildcard '*'")

        parsed = urlparse(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS entries must be valid origins without paths"
            )

        if normalized_env in PRODUCTION_ENVS and _is_localhost_origin(origin):
            raise RuntimeError(
                "Localhost CORS origins are not allowed in production"
            )

        normalized_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if normalized_origin not in seen:
            validated.append(normalized_origin)
            seen.add(normalized_origin)

    if allow_credentials and "*" in validated:
        raise RuntimeError("CORS credentials cannot be enabled with wildcard origins")

    return validated


def get_cors_allowed_origins(app_env: str, allow_credentials: bool) -> list[str]:
    configured_origins = (
        os.getenv("CORS_ALLOWED_ORIGINS")
        or os.getenv("ALLOWED_ORIGINS")
    )
    origins = _split_origins(configured_origins)

    if not origins and app_env in DEVELOPMENT_ENVS:
        origins = list(DEV_DEFAULT_CORS_ORIGINS)

    return validate_cors_origins(
        origins,
        app_env=app_env,
        allow_credentials=allow_credentials,
    )


CORS_ALLOW_CREDENTIALS = _get_bool_env("CORS_ALLOW_CREDENTIALS", False)
CORS_ALLOWED_ORIGINS = get_cors_allowed_origins(APP_ENV, CORS_ALLOW_CREDENTIALS)
CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
]

# =========================
# PUBLIC FRONTEND URL
# Used to build user-facing links (e.g. resume share links) that are
# returned by the API but rendered/opened on the frontend.
# =========================
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://54.92.241.137:3000").rstrip("/")


# =========================
# SENTRY ERROR TRACKING
# =========================
@dataclass(frozen=True)
class SentrySettings:
    dsn: str | None
    environment: str | None
    release: str | None
    traces_sample_rate: float | None


def _get_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


# =========================
# STRUCTURED LOGGING
# =========================
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _get_log_level() -> str:
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if level not in VALID_LOG_LEVELS:
        raise RuntimeError(
            "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
        )
    return level


def _split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _get_optional_int_env(name: str) -> int | None:
    value = _get_optional_env(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning(
            "Ignoring invalid integer environment value for %s",
            name,
        )
        return None


SERVICE_NAME = os.getenv(
    "SERVICE_NAME",
    "nmk-jobportal-userservice",
).strip()
LOG_ENVIRONMENT = os.getenv("LOG_ENVIRONMENT", APP_ENV).strip()
LOG_LEVEL = _get_log_level()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json").strip().lower()
LOG_EXCLUDED_PATHS = _split_csv(
    os.getenv(
        "LOG_EXCLUDED_PATHS",
        "/health,/docs,/redoc,/openapi.json",
    )
)
CLOUDWATCH_LOGGING_ENABLED = _get_bool_env("CLOUDWATCH_LOGGING_ENABLED", False)
CLOUDWATCH_LOG_GROUP = _get_optional_env("CLOUDWATCH_LOG_GROUP")
CLOUDWATCH_LOG_STREAM = _get_optional_env("CLOUDWATCH_LOG_STREAM")
CLOUDWATCH_LOG_RETENTION_DAYS = _get_optional_int_env(
    "CLOUDWATCH_LOG_RETENTION_DAYS"
)


def _parse_sentry_traces_sample_rate(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None

    try:
        sample_rate = float(value)
    except ValueError:
        logger.warning(
            "Ignoring invalid SENTRY_TRACES_SAMPLE_RATE=%r; expected a float from 0.0 to 1.0.",
            value,
        )
        return None

    if 0.0 <= sample_rate <= 1.0:
        return sample_rate

    logger.warning(
        "Ignoring invalid SENTRY_TRACES_SAMPLE_RATE=%r; expected a value from 0.0 to 1.0.",
        value,
    )
    return None


def get_sentry_settings() -> SentrySettings:
    return SentrySettings(
        dsn=_get_optional_env("SENTRY_DSN"),
        environment=_get_optional_env("SENTRY_ENVIRONMENT"),
        release=_get_optional_env("SENTRY_RELEASE"),
        traces_sample_rate=_parse_sentry_traces_sample_rate(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE")
        ),
    )


# =========================
# JWT CONFIG
# =========================
MIN_JWT_SECRET_BYTES = 32
INSECURE_JWT_SECRET_VALUES = {
    "mysecretkey",
    "secret",
    "secretkey",
    "jwtsecret",
    "jwt_secret",
    "changeme",
    "change-me",
    "please-change-me",
    "password",
    "test",
    "testing",
    "development",
    "dev",
    "your-secret-key",
    "replace-me",
    "replace-with-output-of-python-secrets-token-urlsafe-64",
}


def validate_jwt_secret_key(secret: str | None) -> str:
    if secret is None or not secret.strip():
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required"
        )

    normalized = secret.strip()

    if normalized.lower() in INSECURE_JWT_SECRET_VALUES:
        raise RuntimeError(
            "JWT_SECRET_KEY must be a cryptographically secure random secret"
        )

    if len(normalized.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        raise RuntimeError(
            "JWT_SECRET_KEY must be at least 32 bytes"
        )

    return normalized


JWT_SECRET_KEY = validate_jwt_secret_key(os.getenv("JWT_SECRET_KEY"))

DEFAULT_JWT_ALGORITHM = "HS256"


def get_jwt_algorithm(value: str | None = None) -> str:
    configured_algorithm = value if value is not None else os.getenv("ALGORITHM")
    if configured_algorithm is None or not configured_algorithm.strip():
        return DEFAULT_JWT_ALGORITHM

    return configured_algorithm.strip()


ALGORITHM = get_jwt_algorithm()

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        30
    )
)


# =========================
# SMTP CONFIG
# =========================
SMTP_SERVER = os.getenv("SMTP_SERVER")

SMTP_PORT = int(os.getenv("SMTP_PORT",587))

SMTP_USERNAME = os.getenv("SMTP_USERNAME")

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

EMAIL_FROM = os.getenv("EMAIL_FROM")


# =========================
# AWS CONFIG
# =========================
AWS_ACCESS_KEY_ID = os.getenv(
    "AWS_ACCESS_KEY_ID"
)

AWS_SECRET_ACCESS_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY"
)

AWS_SESSION_TOKEN = os.getenv(
    "AWS_SESSION_TOKEN"
)

AWS_REGION = os.getenv(
    "AWS_REGION",
    "us-east-1"
)

BEDROCK_REGION = os.getenv("BEDROCK_REGION", AWS_REGION)
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "openai.gpt-oss-20b-1:0",
)
BEDROCK_TIMEOUT_SECONDS = os.getenv("BEDROCK_TIMEOUT_SECONDS", "30")
BEDROCK_MAX_OUTPUT_CHARS = os.getenv("BEDROCK_MAX_OUTPUT_CHARS", "12000")
BEDROCK_MAX_TOKENS = os.getenv("BEDROCK_MAX_TOKENS", "4000")
BEDROCK_RATE_LIMIT_PER_MINUTE = os.getenv("BEDROCK_RATE_LIMIT_PER_MINUTE", "10")


# =========================
# EMAIL CONFIG (SMTP)
# =========================
SMTP_HOST = os.getenv("SMTP_HOST")

SMTP_PORT = os.getenv("SMTP_PORT")

SMTP_USERNAME = os.getenv("SMTP_USERNAME")

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")

PASSWORD_RESET_URL_BASE = os.getenv("PASSWORD_RESET_URL_BASE")

PASSWORD_RESET_SUBJECT = os.getenv("PASSWORD_RESET_SUBJECT", "Password Reset")

# =========================
# CLOUDFLARE TURNSTILE
# =========================
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY")

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")

TURNSTILE_VERIFY_URL = (
    "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)

# =========================
# LEGACY AI JOB DESCRIPTION
# Older OpenAI-compatible provider settings. Employer AI now uses AWS Bedrock
# through BEDROCK_* settings above.
# =========================
AI_JOB_DESCRIPTION_API_KEY = os.getenv("AI_JOB_DESCRIPTION_API_KEY")
AI_JOB_DESCRIPTION_API_URL = os.getenv("AI_JOB_DESCRIPTION_API_URL")
AI_JOB_DESCRIPTION_MODEL = os.getenv("AI_JOB_DESCRIPTION_MODEL")
AI_JOB_DESCRIPTION_TIMEOUT_SECONDS = os.getenv("AI_JOB_DESCRIPTION_TIMEOUT_SECONDS")
AI_JOB_DESCRIPTION_MAX_OUTPUT_CHARS = os.getenv("AI_JOB_DESCRIPTION_MAX_OUTPUT_CHARS")
AI_JOB_DESCRIPTION_MAX_TOKENS = os.getenv("AI_JOB_DESCRIPTION_MAX_TOKENS")
AI_JOB_DESCRIPTION_RATE_LIMIT_PER_MINUTE = os.getenv(
    "AI_JOB_DESCRIPTION_RATE_LIMIT_PER_MINUTE"
)

# =========================
# OPENAI / APPLICANT RANKING
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE_URL = os.getenv(
    "OPENAI_API_BASE_URL",
    "https://api.openai.com/v1",
).rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "12"))
APPLICANT_RANKING_LLM_ENABLED = (
    os.getenv("APPLICANT_RANKING_LLM_ENABLED", "true").lower() == "true"
)
APPLICANT_RANKING_DETERMINISTIC_WEIGHT = float(
    os.getenv("APPLICANT_RANKING_DETERMINISTIC_WEIGHT", "0.7")
)
APPLICANT_RANKING_SEMANTIC_WEIGHT = float(
    os.getenv("APPLICANT_RANKING_SEMANTIC_WEIGHT", "0.3")
)
APPLICANT_RANKING_MAX_CANDIDATES_PER_REQUEST = int(
    os.getenv("APPLICANT_RANKING_MAX_CANDIDATES_PER_REQUEST", "100")
)

# =========================
# RAZORPAY
# =========================
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
RAZORPAY_API_BASE_URL = os.getenv(
    "RAZORPAY_API_BASE_URL",
    "https://api.razorpay.com/v1",
).rstrip("/")

PAYMENT_RECONCILIATION_ENABLED = (
    os.getenv("PAYMENT_RECONCILIATION_ENABLED", "true").lower() == "true"
)
PAYMENT_RECONCILIATION_INTERVAL_MINUTES = int(
    os.getenv("PAYMENT_RECONCILIATION_INTERVAL_MINUTES", 15)
)
PAYMENT_RECONCILIATION_PENDING_MINUTES = int(
    os.getenv("PAYMENT_RECONCILIATION_PENDING_MINUTES", 5)
)
PAYMENT_RECONCILIATION_STALE_HOURS = int(
    os.getenv("PAYMENT_RECONCILIATION_STALE_HOURS", 24)
)

# ------------------------------------------------------------------
# Development Master OTP (Temporary - Disable in Production)
# ------------------------------------------------------------------

MASTER_OTP_ENABLED = (
    os.getenv("MASTER_OTP_ENABLED", "false").lower() == "true"
)

MASTER_OTP = os.getenv("MASTER_OTP", "")

# ------------------------------------------------------------------
# Authentication Rate Limiting
# ------------------------------------------------------------------

RATE_LIMIT_ENABLED = _get_bool_env("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_STORAGE_URL = os.getenv(
    "RATE_LIMIT_STORAGE_URL",
    "memory://",
).strip()
RATE_LIMIT_TRUSTED_PROXY_IPS = _split_csv(
    os.getenv("RATE_LIMIT_TRUSTED_PROXY_IPS", "127.0.0.1")
)
RATE_LIMIT_REAL_IP_HEADER = os.getenv(
    "RATE_LIMIT_REAL_IP_HEADER",
    "X-Forwarded-For",
).strip()

if RATE_LIMIT_ENABLED and APP_ENV in PRODUCTION_ENVS:
    if not RATE_LIMIT_STORAGE_URL:
        raise RuntimeError(
            "RATE_LIMIT_STORAGE_URL is required when RATE_LIMIT_ENABLED=true "
            "in production"
        )

    if RATE_LIMIT_STORAGE_URL.lower().startswith("memory://"):
        raise RuntimeError(
            "RATE_LIMIT_STORAGE_URL must use Redis-backed storage in production"
        )

    if not RATE_LIMIT_STORAGE_URL.lower().startswith(
        ("redis://", "rediss://", "redis+sentinel://")
    ):
        raise RuntimeError(
            "RATE_LIMIT_STORAGE_URL must be Redis-backed in production"
        )

# ------------------------------------------------------------------
# Super Admin Bootstrap Config
# ------------------------------------------------------------------

SUPER_ADMIN_BOOTSTRAP_ENABLED = (
    os.getenv("SUPER_ADMIN_BOOTSTRAP_ENABLED", "false").lower() == "true"
)

SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")
SUPER_ADMIN_FIRST_NAME = os.getenv("SUPER_ADMIN_FIRST_NAME")
SUPER_ADMIN_LAST_NAME = os.getenv("SUPER_ADMIN_LAST_NAME")
SUPER_ADMIN_MOBILE = os.getenv("SUPER_ADMIN_MOBILE")
SUPER_ADMIN_COUNTRY_CODE = os.getenv("SUPER_ADMIN_COUNTRY_CODE")

# =========================
# JOB ALERT DIGEST SCHEDULER
# =========================
JOB_ALERT_SCHEDULER_ENABLED = (
    os.getenv("JOB_ALERT_SCHEDULER_ENABLED", "true").lower() == "true"
)

JOB_ALERT_DEFAULT_TIMEZONE = os.getenv("JOB_ALERT_DEFAULT_TIMEZONE", "UTC")
JOB_ALERT_SCHEDULER_INTERVAL_MINUTES = int(
    os.getenv("JOB_ALERT_SCHEDULER_INTERVAL_MINUTES", 15)
)

JOB_ALERT_DAILY_HOUR = int(os.getenv("JOB_ALERT_DAILY_HOUR", 8))
JOB_ALERT_DAILY_MINUTE = int(os.getenv("JOB_ALERT_DAILY_MINUTE", 0))

JOB_ALERT_WEEKLY_DAY = os.getenv("JOB_ALERT_WEEKLY_DAY", "monday")
JOB_ALERT_WEEKLY_HOUR = int(os.getenv("JOB_ALERT_WEEKLY_HOUR", 9))
JOB_ALERT_WEEKLY_MINUTE = int(os.getenv("JOB_ALERT_WEEKLY_MINUTE", 0))

# =========================
# DATABASE ENGINE + SESSION FACTORY
# =========================
@dataclass(frozen=True)
class DatabasePoolSettings:
    pool_size: int
    max_overflow: int
    pool_timeout_seconds: int
    pool_recycle_seconds: int
    pool_pre_ping: bool
    connect_timeout_seconds: int
    command_timeout_seconds: int

    @property
    def max_connections_per_process(self) -> int:
        return self.pool_size + self.max_overflow


def get_database_pool_settings() -> DatabasePoolSettings:
    return DatabasePoolSettings(
        pool_size=_get_int_env("DB_POOL_SIZE", 10),
        max_overflow=_get_int_env("DB_MAX_OVERFLOW", 5, minimum=0),
        pool_timeout_seconds=_get_int_env("DB_POOL_TIMEOUT_SECONDS", 10),
        pool_recycle_seconds=_get_int_env("DB_POOL_RECYCLE_SECONDS", 1800),
        pool_pre_ping=_get_bool_env("DB_POOL_PRE_PING", True),
        connect_timeout_seconds=_get_int_env("DB_CONNECT_TIMEOUT_SECONDS", 10),
        command_timeout_seconds=_get_int_env("DB_COMMAND_TIMEOUT_SECONDS", 30),
    )


DB_POOL_SETTINGS = get_database_pool_settings()


def create_database_engine(
    database_url: str,
    settings: DatabasePoolSettings = DB_POOL_SETTINGS,
):
    return create_async_engine(
        database_url,
        future=True,
        echo=False,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        pool_pre_ping=settings.pool_pre_ping,
        connect_args={
            "timeout": settings.connect_timeout_seconds,
            "command_timeout": settings.command_timeout_seconds,
        },
    )


engine = create_database_engine(DATABASE_URL)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a request-scoped AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def commit_rollback(
    session: AsyncSession
):
    try:
        await session.commit()

    except Exception:

        await session.rollback()

        raise
