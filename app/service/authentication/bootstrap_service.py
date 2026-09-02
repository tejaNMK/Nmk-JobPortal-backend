import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    SUPER_ADMIN_BOOTSTRAP_ENABLED,
    SUPER_ADMIN_COUNTRY_CODE,
    SUPER_ADMIN_EMAIL,
    SUPER_ADMIN_FIRST_NAME,
    SUPER_ADMIN_LAST_NAME,
    SUPER_ADMIN_MOBILE,
    SUPER_ADMIN_PASSWORD,
)
from app.repository.authentication.role import RoleRepository
from app.repository.authentication.user_role import UsersRoleRepository
from app.repository.authentication.users import UsersRepository
from app.service.authentication.auth_service import AuthService, pwd_context


logger = logging.getLogger(__name__)

SUPER_ADMIN_ROLE_CODE = "ROLE_SUPER_ADMIN"


class BootstrapService:
    @staticmethod
    def _get_required_config() -> dict:
        config = {
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD,
            "first_name": SUPER_ADMIN_FIRST_NAME,
            "last_name": SUPER_ADMIN_LAST_NAME,
            "mobile_number": SUPER_ADMIN_MOBILE,
            "country_code": SUPER_ADMIN_COUNTRY_CODE,
        }

        missing = [
            env_name
            for env_name, value in {
                "SUPER_ADMIN_EMAIL": config["email"],
                "SUPER_ADMIN_PASSWORD": config["password"],
                "SUPER_ADMIN_FIRST_NAME": config["first_name"],
                "SUPER_ADMIN_LAST_NAME": config["last_name"],
                "SUPER_ADMIN_MOBILE": config["mobile_number"],
                "SUPER_ADMIN_COUNTRY_CODE": config["country_code"],
            }.items()
            if value is None or not str(value).strip()
        ]

        if missing:
            raise RuntimeError(
                "Missing required Super Admin bootstrap environment variables: "
                + ", ".join(missing)
            )

        config["email"] = str(config["email"]).strip().lower()
        config["password"] = str(config["password"])
        config["first_name"] = str(config["first_name"]).strip()
        config["last_name"] = str(config["last_name"]).strip()
        config["mobile_number"] = str(config["mobile_number"]).strip()
        config["country_code"] = str(config["country_code"]).strip()

        return config

    @staticmethod
    def _user_has_super_admin_role(user) -> bool:
        return any(
            getattr(role, "role_code", None) == SUPER_ADMIN_ROLE_CODE
            for role in getattr(user, "roles", []) or []
        )

    @staticmethod
    async def ensure_super_admin(session: AsyncSession):
        if not SUPER_ADMIN_BOOTSTRAP_ENABLED:
            logger.info("Super Admin bootstrap skipped because it is disabled.")
            return {"status": "SKIPPED", "email": None}

        logger.info("Super Admin bootstrap started.")

        try:
            config = BootstrapService._get_required_config()

            role = await RoleRepository.find_by_role_code(
                session,
                SUPER_ADMIN_ROLE_CODE,
            )
            if not role:
                raise RuntimeError("ROLE_SUPER_ADMIN is not configured.")
            if not role.active_flag:
                raise RuntimeError("ROLE_SUPER_ADMIN is inactive and cannot be assigned.")

            logger.info("ROLE_SUPER_ADMIN found for Super Admin bootstrap.")

            user = await UsersRepository.find_by_email(
                session,
                config["email"],
            )

            if user:
                logger.info("Existing user found for Super Admin bootstrap: %s", config["email"])
                if BootstrapService._user_has_super_admin_role(user):
                    logger.info(
                        "Existing user already has ROLE_SUPER_ADMIN: %s",
                        config["email"],
                    )
                    logger.info("Super Admin bootstrap completed for user: %s", config["email"])
                    return {"status": "ALREADY_EXISTS", "email": config["email"]}

                await UsersRoleRepository.assign_role(
                    session=session,
                    user_id=user.user_id,
                    role_id=role.role_id,
                )
                logger.info("Assigned ROLE_SUPER_ADMIN to user: %s", config["email"])
                logger.info("Existing user promoted to Super Admin: %s", config["email"])
                logger.info("Super Admin bootstrap completed for user: %s", config["email"])
                return {"status": "PROMOTED", "email": config["email"]}

            existing_mobile = await UsersRepository.find_by_mobile(
                session,
                config["mobile_number"],
            )
            if existing_mobile:
                raise RuntimeError(
                    "Configured Super Admin mobile number is already assigned "
                    f"to another user: {config['mobile_number']}"
                )

            logger.info("Creating new Super Admin user: %s", config["email"])

            AuthService._passwords_compatible(config["password"])

            user = await UsersRepository.create(
                session=session,
                first_name=config["first_name"],
                last_name=config["last_name"],
                email=config["email"],
                mobile_number=config["mobile_number"],
                country_code=config["country_code"],
                password_hash=pwd_context.hash(config["password"]),
                user_status="ACTIVE",
                email_verified=True,
                mobile_verified=True,
                account_locked=False,
                failed_login_attempts=0,
                deleted_flag=False,
            )

            logger.info("Super Admin user created: %s", config["email"])

            await UsersRoleRepository.assign_role(
                session=session,
                user_id=user.user_id,
                role_id=role.role_id,
            )

            logger.info("Assigned ROLE_SUPER_ADMIN to user: %s", config["email"])
            logger.info("Super Admin bootstrap completed for user: %s", config["email"])

            return {"status": "CREATED", "email": config["email"]}

        except Exception:
            await session.rollback()
            logger.exception("Super Admin bootstrap failed.")
            raise


ensure_super_admin = BootstrapService.ensure_super_admin
