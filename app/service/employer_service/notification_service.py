from __future__ import annotations

from datetime import date, timedelta
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.schema.notification import (
    EmployerNotificationListData,
    EmployerUnreadCountData,
    NotificationDeletedCountData,
    NotificationCountSchema,
    NotificationUpdatedCountData,
    PaginationSchema,
)
from app.service.notification_service import NotificationService
from app.utils.date_range import normalize_date_range


class EmployerNotificationService:
    @staticmethod
    def _recipient_id(payload: dict) -> str:
        return str(payload.get("user_id"))

    @classmethod
    async def list_notifications(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
        page: int,
        page_size: int,
        is_read: bool | None = None,
        notification_type: str | None = None,
        filter: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        timezone: str | None = None,
        search: str | None = None,
        sort_order: str = "desc",
    ) -> EmployerNotificationListData:
        recipient_id = cls._recipient_id(payload)
        resolved_is_read = cls._resolve_read_filter(is_read, filter)
        date_range = cls._resolve_date_filter(
            filter=filter,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone,
        )
        notification_types = cls._resolve_type_filters(
            category=category or filter,
            priority=priority,
        )
        total = await NotificationService.count_notifications(
            session=session,
            recipient_id=recipient_id,
            is_read=resolved_is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            date_range=date_range,
            search=search,
        )
        items = await NotificationService.get_notifications(
            session=session,
            recipient_id=recipient_id,
            page=page,
            page_size=page_size,
            is_read=resolved_is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            date_range=date_range,
            search=search,
            sort_order=sort_order,
        )
        counts = await NotificationService.get_count_summary(
            session=session,
            recipient_id=recipient_id,
        )
        total_pages = ceil(total / page_size) if total else 0

        return EmployerNotificationListData(
            items=NotificationService.format_notifications(items),
            pagination=PaginationSchema(
                page=page,
                page_size=page_size,
                total=total,
                total_items=total,
                total_pages=total_pages,
                next_page=page + 1 if page < total_pages else None,
                previous_page=page - 1 if page > 1 and total_pages else None,
            ),
            unread_count=counts["unread_notifications"],
            counts=NotificationCountSchema(**counts),
            range=date_range.as_response() if date_range else None,
        )

    @classmethod
    async def unread_count(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
    ) -> EmployerUnreadCountData:
        counts = await NotificationService.get_count_summary(
            session=session,
            recipient_id=cls._recipient_id(payload),
        )
        return EmployerUnreadCountData(
            **counts,
            unread_count=counts["unread_notifications"],
        )

    @classmethod
    async def mark_as_read(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
        notification_id: str,
    ) -> NotificationUpdatedCountData:
        updated = await NotificationService.mark_as_read(
            session=session,
            notification_id=notification_id,
            recipient_id=cls._recipient_id(payload),
        )
        return NotificationUpdatedCountData(updated_count=1 if updated else 0)

    @classmethod
    async def mark_all_as_read(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
    ) -> NotificationUpdatedCountData:
        return NotificationUpdatedCountData(
            updated_count=await NotificationService.mark_all_as_read(
                session=session,
                recipient_id=cls._recipient_id(payload),
            )
        )

    @classmethod
    async def mark_many_as_read(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
        notification_ids: list[str],
    ) -> NotificationUpdatedCountData:
        return NotificationUpdatedCountData(
            updated_count=await NotificationService.mark_many_as_read(
                session=session,
                notification_ids=notification_ids,
                recipient_id=cls._recipient_id(payload),
            )
        )

    @classmethod
    async def delete_notification(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
        notification_id: str,
    ) -> NotificationDeletedCountData:
        deleted = await NotificationService.delete_notification(
            session=session,
            notification_id=notification_id,
            recipient_id=cls._recipient_id(payload),
        )
        return NotificationDeletedCountData(deleted_count=1 if deleted else 0)

    @classmethod
    async def clear_read_notifications(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
    ) -> NotificationDeletedCountData:
        return NotificationDeletedCountData(
            deleted_count=await NotificationService.clear_read_for_user(
                session=session,
                recipient_id=cls._recipient_id(payload),
            )
        )

    @classmethod
    async def delete_many(
        cls,
        *,
        session: AsyncSession,
        payload: dict,
        notification_ids: list[str],
    ) -> NotificationDeletedCountData:
        return NotificationDeletedCountData(
            deleted_count=await NotificationService.delete_many(
                session=session,
                notification_ids=notification_ids,
                recipient_id=cls._recipient_id(payload),
            )
        )

    @staticmethod
    def _resolve_read_filter(
        is_read: bool | None,
        filter: str | None,
    ) -> bool | None:
        if is_read is not None:
            return is_read
        normalized = (filter or "").strip().upper().replace(" ", "_")
        if normalized == "UNREAD":
            return False
        if normalized == "READ":
            return True
        return None

    @staticmethod
    def _resolve_date_filter(
        *,
        filter: str | None,
        from_date: str | None,
        to_date: str | None,
        timezone: str | None,
    ):
        normalized = (filter or "").strip().upper().replace(" ", "_")
        today = date.today()
        if normalized == "TODAY":
            return normalize_date_range(
                from_date=today,
                to_date=today,
                timezone_name=timezone,
            )
        if normalized == "THIS_WEEK":
            week_start = today - timedelta(days=today.weekday())
            return normalize_date_range(
                from_date=week_start,
                to_date=today,
                timezone_name=timezone,
            )
        if from_date or to_date:
            return normalize_date_range(
                from_date=from_date,
                to_date=to_date,
                timezone_name=timezone,
            )
        return None

    @staticmethod
    def _resolve_type_filters(
        *,
        category: str | None,
        priority: str | None,
    ) -> list[str] | None:
        category_types = NotificationService.get_types_for_category(category)
        priority_types = NotificationService.get_types_for_priority(priority)
        if category_types and priority_types:
            return sorted(set(category_types).intersection(priority_types))
        return category_types or priority_types
