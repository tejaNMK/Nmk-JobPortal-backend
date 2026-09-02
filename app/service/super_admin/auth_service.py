from fastapi import HTTPException

from app.schema.auth import LoginSchema
from app.service.authentication.auth_service import AuthService
from app.service.super_admin.activity_log_service import ActivityLogService


def _normalize_role_code(value: str | None) -> str | None:
    if not value:
        return None

    normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    if not normalized.startswith("ROLE_"):
        normalized = f"ROLE_{normalized}"

    return normalized


class SuperAdminAuthService:

    @staticmethod
    async def login(
        session,
        login: LoginSchema,
        ip_address: str | None = None,
    ):

        # Validate credentials and create JWT
        token_data = await AuthService.login_service(
            session=session,
            login=login,
            log_activity=False,
        )

        # Fetch authenticated user (includes roles)
        user = await AuthService.authenticate_user(
            session=session,
            login=login,
        )

        role_codes = {
            normalized
            for role in user["roles"]
            for normalized in (
                _normalize_role_code(role.get("role_code")),
                _normalize_role_code(role.get("role_name")),
            )
            if normalized
        }

        if "ROLE_SUPER_ADMIN" not in role_codes:
            raise HTTPException(
                status_code=403,
                detail="Only Super Admins can login.",
            )

        await ActivityLogService.create_log(
            session=session,
            actor=user,
            action="LOGIN",
            entity_type="SuperAdmin",
            entity_id=user["user_id"],
            description="Super Admin logged in",
            ip_address=ip_address,
        )

        return {
            **token_data,
            "user": user,
        }
