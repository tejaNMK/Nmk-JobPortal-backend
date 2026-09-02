from fastapi import HTTPException
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.authentication.users import UsersRepository
from app.repository.super_admin.settings_repo import SystemSettingsRepository
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.schema.super_admin.settings import (
    SystemSettingsResponse,
    SystemSettingsUpdateRequest,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService
from app.service.subscription.subscription_bootstrap_service import (
    SubscriptionBootstrapService,
)


class SystemSettingsService:
    PASSWORD_POLICY_FIELDS = {
        "minimum_password_length",
        "require_uppercase",
        "require_lowercase",
        "require_number",
        "require_special_character",
    }
    EMAIL_NOTIFICATION_FIELDS = {
        "master_email_notifications",
        "company_approval_updates",
        "subscription_updates",
        "system_alerts",
    }
    PLATFORM_CONFIG_FIELDS = {
        "platform_name",
        "support_email",
        "timezone",
    }
    DEFAULT_PLAN_FIELDS = {
        "candidate_default_subscription_plan": "CANDIDATE",
        "employer_default_subscription_plan": "EMPLOYER",
    }

    @staticmethod
    async def get_settings(session: AsyncSession) -> SystemSettingsResponse:
        settings = await SystemSettingsRepository.get_active(session)
        if not settings:
            settings = await SystemSettingsRepository.create_default(session)
        return await SystemSettingsService._build_response(
            session=session,
            settings=settings,
        )

    @staticmethod
    def _role_code_from_user(user) -> str | None:
        for role in getattr(user, "roles", []) or []:
            role_code = getattr(role, "role_code", None)
            if role_code:
                return str(role_code)
        return None

    @staticmethod
    def _display_name_from_user(user) -> str:
        full_name = " ".join(
            part.strip()
            for part in (
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            )
            if isinstance(part, str) and part.strip()
        )
        if full_name:
            return full_name

        for attr in ("display_name", "username", "email"):
            value = getattr(user, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return "Unknown User"

    @staticmethod
    async def _resolve_updated_by_details(
        session: AsyncSession,
        updated_by: str | None,
    ) -> dict[str, str | None]:
        if not updated_by:
            return {
                "updated_by_email": None,
                "updated_by_name": None,
                "updated_by_role": None,
            }

        try:
            user = await UsersRepository.find_by_user_id(session, updated_by)
        except Exception:
            user = None

        if not user:
            return {
                "updated_by_email": None,
                "updated_by_name": "Unknown User",
                "updated_by_role": None,
            }

        return {
            "updated_by_email": getattr(user, "email", None),
            "updated_by_name": SystemSettingsService._display_name_from_user(user),
            "updated_by_role": SystemSettingsService._role_code_from_user(user),
        }

    @staticmethod
    async def _build_response(
        session: AsyncSession,
        settings,
    ) -> SystemSettingsResponse:
        response = SystemSettingsResponse.model_validate(
            settings,
            from_attributes=True,
        )
        audit_details = await SystemSettingsService._resolve_updated_by_details(
            session=session,
            updated_by=response.updated_by,
        )
        return response.model_copy(update=audit_details)

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(
                exclude_none=True,
                by_alias=False,
            )
        return value

    @staticmethod
    def _normalize_patch_data(request: SystemSettingsUpdateRequest) -> dict:
        raw_data = {
            key: SystemSettingsService._normalize_value(value)
            for key, value in request.model_dump(exclude_unset=True).items()
        }
        updates: dict[str, Any] = {}

        for key in (
            "maintenance_mode",
            "registration_enabled",
            "candidate_default_subscription_plan",
            "employer_default_subscription_plan",
        ):
            if key in raw_data:
                updates[key] = raw_data[key]

        password_policy = dict(raw_data.get("password_policy") or {})
        if "minimum_password_length" in password_policy:
            password_policy["min_length"] = password_policy.pop(
                "minimum_password_length"
            )
        for key in SystemSettingsService.PASSWORD_POLICY_FIELDS:
            if key in raw_data:
                target_key = "min_length" if key == "minimum_password_length" else key
                password_policy[target_key] = raw_data[key]
        if password_policy:
            updates["password_policy"] = password_policy

        email_notifications = dict(raw_data.get("email_notifications") or {})
        if "master_email_notifications" in email_notifications:
            email_notifications["enabled"] = email_notifications.pop(
                "master_email_notifications"
            )
        for key in SystemSettingsService.EMAIL_NOTIFICATION_FIELDS:
            if key in raw_data:
                target_key = "enabled" if key == "master_email_notifications" else key
                email_notifications[target_key] = raw_data[key]
        if email_notifications:
            updates["email_notifications"] = email_notifications

        platform_config = dict(raw_data.get("platform_config") or {})
        for key in SystemSettingsService.PLATFORM_CONFIG_FIELDS:
            if key in raw_data:
                platform_config[key] = raw_data[key]
        if platform_config:
            updates["platform_config"] = platform_config

        return updates

    @staticmethod
    async def _validate_default_plan(
        session: AsyncSession,
        *,
        field: str,
        plan_id: str,
    ) -> str:
        try:
            subscription_id = UUID(str(plan_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Default subscription plan must be a subscription ID.",
            ) from exc

        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription_id,
        )
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )
        if not subscription.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive subscription plans cannot be default.",
            )

        expected_type = SystemSettingsService.DEFAULT_PLAN_FIELDS[field]
        subscription_type = (subscription.subscription_type or "").upper()
        if subscription_type != expected_type:
            label = "candidate" if expected_type == "CANDIDATE" else "employer"
            raise HTTPException(
                status_code=400,
                detail=f"{label.title()} default plan must be a {label} subscription.",
            )

        await SubscriptionRepository.clear_default_for_type(
            session=session,
            subscription_type=subscription.subscription_type,
            exclude_subscription_id=subscription.subscription_id,
        )
        subscription.is_default = True
        session.add(subscription)
        return str(subscription.subscription_id)

    @staticmethod
    async def update_settings(
        session: AsyncSession,
        request: SystemSettingsUpdateRequest,
        actor,
    ) -> SystemSettingsResponse:
        settings = await SystemSettingsRepository.get_active(session)
        if not settings:
            settings = await SystemSettingsRepository.create_default(session)

        data = SystemSettingsService._normalize_patch_data(request)
        for field in SystemSettingsService.DEFAULT_PLAN_FIELDS:
            if field in data and data[field]:
                data[field] = await SystemSettingsService._validate_default_plan(
                    session=session,
                    field=field,
                    plan_id=data[field],
                )

        updated_by = str(actor.get("user_id")) if isinstance(actor, dict) else None
        settings = await SystemSettingsRepository.update(
            session=session,
            settings=settings,
            updates=data,
            updated_by=updated_by,
        )
        if any(field in data for field in SystemSettingsService.DEFAULT_PLAN_FIELDS):
            await SubscriptionBootstrapService.backfill_missing_user_subscriptions(
                session=session,
            )

        action = "SYSTEM_SETTINGS_UPDATED"
        if "maintenance_mode" in data:
            action = (
                "MAINTENANCE_MODE_ENABLED"
                if data["maintenance_mode"]
                else "MAINTENANCE_MODE_DISABLED"
            )
        elif "registration_enabled" in data:
            action = (
                "REGISTRATION_ENABLED"
                if data["registration_enabled"]
                else "REGISTRATION_DISABLED"
            )
        elif "platform_config" in data:
            action = "PLATFORM_CONFIGURATION_UPDATED"

        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action=action,
            entity_type="SystemSettings",
            entity_id=settings.id,
            description="Updated system settings",
            metadata={"updated_fields": sorted(data.keys())},
        )
        if action in {
            "MAINTENANCE_MODE_ENABLED",
            "MAINTENANCE_MODE_DISABLED",
            "REGISTRATION_ENABLED",
            "REGISTRATION_DISABLED",
        }:
            await NotificationService.create_for_super_admins(
                session,
                notification_type=action,
                title=action.replace("_", " ").title(),
                message="System setting changed.",
                entity_type="setting",
                entity_id=str(settings.id),
                target_route="/super-admin/settings",
                metadata={"updated_fields": sorted(data.keys())},
                event_key=f"{action.lower()}:{settings.id}:{settings.updated_at}",
                commit=True,
            )
        return await SystemSettingsService._build_response(
            session=session,
            settings=settings,
        )
