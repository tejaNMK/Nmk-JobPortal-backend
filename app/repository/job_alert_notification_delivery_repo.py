from __future__ import annotations

from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.notification_constants import NotificationDeliveryStatus
from app.model.candidate_model.job_alert_notification_delivery import (
    JobAlertNotificationDelivery,
)


class JobAlertNotificationDeliveryRepo:
    @classmethod
    async def reserve_delivery(
        cls,
        *,
        session: AsyncSession,
        candidate_id: str | None,
        recipient_id: str,
        alert_id: str | None,
        job_id: str | None,
        frequency: str,
        notification_type: str,
        channel: str,
        delivery_key: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> JobAlertNotificationDelivery | None:
        delivery = JobAlertNotificationDelivery(
            candidate_id=candidate_id,
            recipient_id=recipient_id,
            alert_id=alert_id,
            job_id=job_id,
            frequency=frequency,
            notification_type=notification_type,
            channel=channel,
            delivery_key=delivery_key,
            window_start=window_start,
            window_end=window_end,
            status=NotificationDeliveryStatus.PENDING,
            attempt_count=1,
            created_at=utc_now_naive(),
        )

        try:
            session.add(delivery)
            await session.commit()
            await session.refresh(delivery)
            return delivery
        except IntegrityError:
            await session.rollback()

        existing = await cls.get_by_delivery_key(
            session=session,
            delivery_key=delivery_key,
        )
        if existing is None:
            return None

        if existing.status != NotificationDeliveryStatus.FAILED:
            return None

        await session.execute(
            update(JobAlertNotificationDelivery)
            .where(
                JobAlertNotificationDelivery.id == existing.id,
                JobAlertNotificationDelivery.status
                == NotificationDeliveryStatus.FAILED,
            )
            .values(
                status=NotificationDeliveryStatus.PENDING,
                attempt_count=JobAlertNotificationDelivery.attempt_count + 1,
                failed_at=None,
                last_error=None,
            )
        )
        await session.commit()
        return await cls.get_by_delivery_key(
            session=session,
            delivery_key=delivery_key,
        )

    @classmethod
    async def get_by_delivery_key(
        cls,
        *,
        session: AsyncSession,
        delivery_key: str,
    ) -> JobAlertNotificationDelivery | None:
        result = await session.execute(
            select(JobAlertNotificationDelivery).where(
                JobAlertNotificationDelivery.delivery_key == delivery_key,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def mark_sent(
        cls,
        *,
        session: AsyncSession,
        delivery_id: str,
    ) -> None:
        await session.execute(
            update(JobAlertNotificationDelivery)
            .where(JobAlertNotificationDelivery.id == delivery_id)
            .values(
                status=NotificationDeliveryStatus.SENT,
                sent_at=utc_now_naive(),
                failed_at=None,
                last_error=None,
            )
        )
        await session.commit()

    @classmethod
    async def mark_failed(
        cls,
        *,
        session: AsyncSession,
        delivery_id: str,
        error: str,
    ) -> None:
        await session.execute(
            update(JobAlertNotificationDelivery)
            .where(JobAlertNotificationDelivery.id == delivery_id)
            .values(
                status=NotificationDeliveryStatus.FAILED,
                failed_at=utc_now_naive(),
                last_error=error,
            )
        )
        await session.commit()
