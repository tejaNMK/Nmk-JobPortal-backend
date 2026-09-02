from __future__ import annotations

import hashlib
import ipaddress
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from fastapi import HTTPException, Request

from app.config import (
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_REAL_IP_HEADER,
    RATE_LIMIT_STORAGE_URL,
    RATE_LIMIT_TRUSTED_PROXY_IPS,
)


RATE_LIMIT_MESSAGE = "Too many requests. Please try again later."


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int
    key_builder: Callable[[Request, Any | None], str | None]


class InMemoryFixedWindowStorage:
    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.time()
        count, reset_at = self._hits.get(key, (0, now + window_seconds))

        if now >= reset_at:
            count = 0
            reset_at = now + window_seconds

        count += 1
        self._hits[key] = (count, reset_at)
        retry_after = max(1, int(reset_at - now))
        remaining = max(0, limit - count)
        return count <= limit, retry_after, remaining

    def reset(self) -> None:
        self._hits.clear()


class LimitsFixedWindowStorage:
    def __init__(self, storage_url: str) -> None:
        try:
            from limits import RateLimitItemPerSecond
            from limits.storage import storage_from_string
            from limits.strategies import FixedWindowRateLimiter
        except ImportError as exc:
            raise RuntimeError(
                "slowapi and redis dependencies are required for Redis-backed "
                "rate limiting. Install requirements.txt."
            ) from exc

        self._item_class = RateLimitItemPerSecond
        self._storage = storage_from_string(storage_url)
        self._limiter = FixedWindowRateLimiter(self._storage)

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        item = self._item_class(limit, window_seconds)
        allowed = self._limiter.hit(item, key)
        window = self._limiter.get_window_stats(item, key)
        reset_at = getattr(window, "reset_time", time.time() + window_seconds)
        remaining = getattr(window, "remaining", 0)
        retry_after = max(1, int(reset_at - time.time()))
        return allowed, retry_after, max(0, int(remaining))

    def reset(self) -> None:
        reset = getattr(self._storage, "reset", None)
        if callable(reset):
            reset()


class AuthRateLimiter:
    def __init__(self) -> None:
        self.enabled = RATE_LIMIT_ENABLED
        self.storage_url = RATE_LIMIT_STORAGE_URL
        if not self.enabled:
            self.storage: InMemoryFixedWindowStorage | LimitsFixedWindowStorage
        elif self.storage_url.lower().startswith("memory://"):
            self.storage = InMemoryFixedWindowStorage()
        else:
            self.storage = LimitsFixedWindowStorage(self.storage_url)

    async def check(
        self,
        request: Request,
        body: Any | None,
        rules: Iterable[RateLimitRule],
    ) -> None:
        if not self.enabled:
            return

        for rule in rules:
            key = rule.key_builder(request, body)
            if not key:
                continue

            allowed, retry_after, _remaining = self.storage.hit(
                key=f"{rule.name}:{key}",
                limit=rule.limit,
                window_seconds=rule.window_seconds,
            )
            if not allowed:
                raise rate_limit_exceeded(retry_after)

    def reset(self) -> None:
        if self.enabled:
            self.storage.reset()


def rate_limit_exceeded(retry_after: int | None = None) -> HTTPException:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(max(1, int(retry_after)))
    return HTTPException(
        status_code=429,
        detail={
            "message": RATE_LIMIT_MESSAGE,
            "code": "TOO_MANY_REQUESTS",
            "details": RATE_LIMIT_MESSAGE,
        },
        headers=headers,
    )


def configure_slowapi_limiter(app) -> None:
    """Attach SlowAPI's Limiter for app-level integration.

    Auth endpoint enforcement below uses this module's central policy helpers so
    composite IP + identifier keys can be built from validated request bodies.
    """
    if not RATE_LIMIT_ENABLED:
        return

    try:
        from slowapi import Limiter
    except ImportError:
        if not RATE_LIMIT_STORAGE_URL.lower().startswith("memory://"):
            raise RuntimeError(
                "slowapi is required for Redis-backed authentication rate limiting"
            )
        return

    app.state.limiter = Limiter(
        key_func=get_client_ip,
        storage_uri=RATE_LIMIT_STORAGE_URL,
        enabled=RATE_LIMIT_ENABLED,
    )


def normalize_email(value: Any | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def normalize_phone(value: Any | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(char for char in str(value).strip() if char.isdigit() or char == "+")
    return normalized or None


def hash_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    networks: list[ipaddress._BaseNetwork] = []
    for raw in RATE_LIMIT_TRUSTED_PROXY_IPS:
        try:
            if "/" in raw:
                networks.append(ipaddress.ip_network(raw, strict=False))
            else:
                networks.append(ipaddress.ip_network(f"{raw}/32", strict=False))
        except ValueError:
            continue
    return networks


def is_trusted_proxy(ip_value: str | None) -> bool:
    if not ip_value:
        return False
    try:
        address = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def _first_forwarded_ip(header_value: str | None) -> str | None:
    if not header_value:
        return None
    for part in header_value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return candidate
    return None


def get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else None
    if is_trusted_proxy(direct_ip):
        forwarded_ip = _first_forwarded_ip(
            request.headers.get(RATE_LIMIT_REAL_IP_HEADER)
        )
        if forwarded_ip:
            return forwarded_ip
    return direct_ip or "unknown"


def _body_value(body: Any | None, *names: str) -> Any | None:
    for name in names:
        if isinstance(body, dict) and name in body:
            return body.get(name)
        if body is not None and hasattr(body, name):
            return getattr(body, name)
    return None


def _ip_key(scope: str) -> Callable[[Request, Any | None], str]:
    def build(request: Request, body: Any | None) -> str:
        return f"auth:{scope}:ip:{hash_identifier(get_client_ip(request))}"

    return build


def _identifier_key(
    scope: str,
    *fields: str,
    normalizer: Callable[[Any | None], str | None],
) -> Callable[[Request, Any | None], str | None]:
    def build(request: Request, body: Any | None) -> str | None:
        raw = _body_value(body, *fields)
        normalized = normalizer(raw)
        hashed = hash_identifier(normalized)
        if not hashed:
            return None
        return f"auth:{scope}:id:{hashed}"

    return build


def _ip_identifier_key(
    scope: str,
    *fields: str,
    normalizer: Callable[[Any | None], str | None],
) -> Callable[[Request, Any | None], str | None]:
    def build(request: Request, body: Any | None) -> str | None:
        raw = _body_value(body, *fields)
        normalized = normalizer(raw)
        hashed = hash_identifier(normalized)
        if not hashed:
            return None
        ip_hash = hash_identifier(get_client_ip(request))
        return f"auth:{scope}:ip_id:{ip_hash}:{hashed}"

    return build


def _authenticated_user_key(scope: str) -> Callable[[Request, Any | None], str | None]:
    def build(request: Request, body: Any | None) -> str | None:
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            return None
        user_id = payload.get("user_id")
        hashed = hash_identifier(str(user_id)) if user_id else None
        if not hashed:
            return None
        return f"auth:{scope}:user:{hashed}"

    return build


def _rules(scope: str, specs: list[tuple[str, int, int, Callable]]) -> list[RateLimitRule]:
    return [
        RateLimitRule(
            name=f"{scope}:{name}",
            limit=limit,
            window_seconds=window_seconds,
            key_builder=builder,
        )
        for name, limit, window_seconds, builder in specs
    ]


LOGIN_RULES = _rules(
    "login",
    [
        ("ip_minute", 5, 60, _ip_key("login")),
        ("ip_hour", 20, 3600, _ip_key("login")),
        ("email_ip_minute", 5, 60, _ip_identifier_key("login", "email", normalizer=normalize_email)),
        ("email_ip_hour", 20, 3600, _ip_identifier_key("login", "email", normalizer=normalize_email)),
    ],
)

SUPER_ADMIN_LOGIN_RULES = _rules(
    "super_admin_login",
    [
        ("ip_minute", 3, 60, _ip_key("super_admin_login")),
        ("ip_hour", 10, 3600, _ip_key("super_admin_login")),
        ("email_ip_minute", 3, 60, _ip_identifier_key("super_admin_login", "email", normalizer=normalize_email)),
        ("email_ip_hour", 10, 3600, _ip_identifier_key("super_admin_login", "email", normalizer=normalize_email)),
    ],
)

CANDIDATE_REGISTER_RULES = _rules(
    "candidate_register",
    [
        ("ip", 5, 600, _ip_key("candidate_register")),
        ("email", 5, 600, _identifier_key("candidate_register", "email", normalizer=normalize_email)),
        ("phone", 5, 600, _identifier_key("candidate_register", "phone_number", normalizer=normalize_phone)),
    ],
)

EMPLOYER_REGISTER_RULES = _rules(
    "employer_register",
    [
        ("ip", 3, 600, _ip_key("employer_register")),
        ("email", 3, 600, _identifier_key("employer_register", "work_email", "email", normalizer=normalize_email)),
        ("phone", 3, 600, _identifier_key("employer_register", "phone_number", normalizer=normalize_phone)),
    ],
)

SEND_EMAIL_OTP_RULES = _rules(
    "send_email_otp",
    [
        ("ip", 3, 300, _ip_key("send_email_otp")),
        ("email_ip", 3, 300, _ip_identifier_key("send_email_otp", "email", normalizer=normalize_email)),
        ("email", 3, 300, _identifier_key("send_email_otp", "email", normalizer=normalize_email)),
    ],
)

VERIFY_EMAIL_OTP_RULES = _rules(
    "verify_email_otp",
    [
        ("ip", 5, 300, _ip_key("verify_email_otp")),
        ("email_ip", 5, 300, _ip_identifier_key("verify_email_otp", "email", normalizer=normalize_email)),
        ("email", 5, 300, _identifier_key("verify_email_otp", "email", normalizer=normalize_email)),
    ],
)

SEND_MOBILE_OTP_RULES = _rules(
    "send_mobile_otp",
    [
        ("ip", 3, 600, _ip_key("send_mobile_otp")),
        ("phone_ip", 3, 600, _ip_identifier_key("send_mobile_otp", "phone_number", normalizer=normalize_phone)),
        ("phone", 3, 600, _identifier_key("send_mobile_otp", "phone_number", normalizer=normalize_phone)),
    ],
)

VERIFY_MOBILE_OTP_RULES = _rules(
    "verify_mobile_otp",
    [
        ("ip", 5, 300, _ip_key("verify_mobile_otp")),
        ("phone_ip", 5, 300, _ip_identifier_key("verify_mobile_otp", "phone_number", normalizer=normalize_phone)),
        ("phone", 5, 300, _identifier_key("verify_mobile_otp", "phone_number", normalizer=normalize_phone)),
    ],
)

FORGOT_PASSWORD_RULES = _rules(
    "forgot_password",
    [
        ("ip", 3, 600, _ip_key("forgot_password")),
        ("email", 3, 600, _identifier_key("forgot_password", "email", normalizer=normalize_email)),
        ("phone", 3, 600, _identifier_key("forgot_password", "mobile_number", normalizer=normalize_phone)),
    ],
)

RESET_PASSWORD_RULES = _rules(
    "reset_password",
    [
        ("ip", 5, 600, _ip_key("reset_password")),
        ("email", 5, 600, _identifier_key("reset_password", "email", normalizer=normalize_email)),
        ("phone", 5, 600, _identifier_key("reset_password", "mobile_number", normalizer=normalize_phone)),
    ],
)

FORGOT_USERID_RULES = _rules(
    "forgot_userid",
    [
        ("ip", 3, 600, _ip_key("forgot_userid")),
        ("email", 3, 600, _identifier_key("forgot_userid", "email", normalizer=normalize_email)),
        ("phone", 3, 600, _identifier_key("forgot_userid", "mobile_number", normalizer=normalize_phone)),
    ],
)

CHANGE_PASSWORD_RULES = _rules(
    "change_password",
    [
        ("ip", 5, 600, _ip_key("change_password")),
        ("user", 5, 600, _authenticated_user_key("change_password")),
    ],
)


auth_rate_limiter = AuthRateLimiter()


def get_auth_rate_limiter() -> AuthRateLimiter:
    return auth_rate_limiter
