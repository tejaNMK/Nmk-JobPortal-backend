from sqlalchemy.exc import InterfaceError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import AsyncSessionLocal, engine
from app.repository.authentication.auth_repo import JWTRepo
from app.repository.authentication.users import UsersRepository
from app.repository.super_admin.settings_repo import SystemSettingsRepository


MAINTENANCE_MESSAGE = (
    "The platform is currently under maintenance. Please try again later."
)
REGISTRATION_DISABLED_MESSAGE = "Registration is currently disabled."

SUPER_ADMIN_PREFIX = "/super-admin"
REGISTRATION_PATHS = {
    "/auth/candidate/register",
    "/auth/employer/register",
}
HEALTH_CHECK_PATH = "/health"


def _normalize_role_code(value: str | None) -> str | None:
    if not value:
        return None

    normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    if not normalized.startswith("ROLE_"):
        normalized = f"ROLE_{normalized}"

    return normalized


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path == HEALTH_CHECK_PATH:
            return await call_next(request)

        blocked_response = None
        allow_request = False

        settings, is_super_admin = await self._load_request_context(request)

        if not settings:
            allow_request = True

        elif (
            not settings.registration_enabled
            and path in REGISTRATION_PATHS
        ):
            blocked_response = JSONResponse(
                status_code=403,
                content={"message": REGISTRATION_DISABLED_MESSAGE},
            )

        elif not settings.maintenance_mode:
            allow_request = True

        elif path.startswith(SUPER_ADMIN_PREFIX):
            allow_request = True

        elif is_super_admin:
            allow_request = True

        if allow_request:
            return await call_next(request)

        if blocked_response:
            return blocked_response

        return JSONResponse(
            status_code=503,
            content={"message": MAINTENANCE_MESSAGE},
        )

    async def _load_request_context(self, request):
        try:
            return await self._load_request_context_once(request)
        except (InterfaceError, AttributeError) as exc:
            if not self._is_recoverable_connection_error(exc):
                raise
            await engine.dispose()
            return await self._load_request_context_once(request)

    async def _load_request_context_once(self, request):
        async with AsyncSessionLocal() as session:
            settings = await SystemSettingsRepository.get_active(session)
            is_super_admin = False
            if settings and settings.maintenance_mode:
                is_super_admin = await self._is_super_admin_request(request, session)
            return settings, is_super_admin

    @staticmethod
    def _is_recoverable_connection_error(exc: Exception) -> bool:
        if isinstance(exc, InterfaceError):
            return True
        return "'NoneType' object has no attribute 'send'" in str(exc)

    @staticmethod
    async def _is_super_admin_request(request, session) -> bool:
        auth_header = (
            request.headers.get("Authorization")
            or request.headers.get("authorization")
        )
        if not auth_header:
            return False

        parts = auth_header.strip().split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False

        payload = JWTRepo.extract_token(parts[1].strip())
        if not payload:
            return False

        user_id = payload.get("user_id")
        if not user_id:
            return False

        user = await UsersRepository.find_by_user_id(
            session=session,
            user_id=user_id,
        )
        if not user:
            return False

        return any(
            _normalize_role_code(value) == "ROLE_SUPER_ADMIN"
            for role in getattr(user, "roles", []) or []
            for value in (
                getattr(role, "role_code", None),
                getattr(role, "role_name", None),
            )
        )
