from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.system_settings import SystemSettings


class SystemSettingsRepository:
    @staticmethod
    async def get_active(session: AsyncSession) -> SystemSettings | None:
        result = await session.execute(
            select(SystemSettings)
            .where(SystemSettings.is_active.is_(True))
            .order_by(SystemSettings.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_default(session: AsyncSession) -> SystemSettings:
        settings = SystemSettings()
        session.add(settings)
        await commit_rollback(session)
        await session.refresh(settings)
        return settings

    @staticmethod
    async def update(
        session: AsyncSession,
        settings: SystemSettings,
        updates: dict,
        updated_by: str | None = None,
    ) -> SystemSettings:
        for key, value in updates.items():
            if key in {"password_policy", "email_notifications", "platform_config"}:
                existing = getattr(settings, key) or {}
                setattr(settings, key, {**existing, **value})
                continue
            setattr(settings, key, value)
        settings.updated_at = utc_now_naive()
        settings.updated_by = updated_by
        await commit_rollback(session)
        await session.refresh(settings)
        return settings
