from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.model.authentication.role import Role
from app.model.authentication.users import Users

from app.model.notification import Notification
from app.utils.date_range import NormalizedDateRange, normalize_datetime_for_db


class NotificationRepo:
    @staticmethod
    def _recipient_filter(recipient_id: str):
        return or_(
            Notification.recipient_user_id == recipient_id,
            Notification.recipient_id == recipient_id,
        )

    @classmethod
    async def create_notification(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        title: str,
        message: str,
        notification_type: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        recipient_role: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        target_route: str | None = None,
        metadata: dict | None = None,
        event_key: str | None = None,
        commit: bool = True,
    ) -> Notification:

        notification = Notification(
            recipient_id=recipient_id,
            recipient_user_id=recipient_id,
            recipient_role=recipient_role,
            title=title,
            message=message,
            notification_type=notification_type,
            reference_type=reference_type,
            reference_id=reference_id,
            entity_type=entity_type or reference_type,
            entity_id=entity_id or reference_id,
            target_route=target_route,
            metadata_=metadata,
            event_key=event_key,
            is_read=False,
            read_at=None,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )

        try:
            session.add(notification)
            if commit:
                await session.commit()
                await session.refresh(notification)
            elif hasattr(session, "flush"):
                await session.flush()

            return notification

        except IntegrityError:
            if commit:
                await session.rollback()
            raise
        except Exception:
            if commit:
                await session.rollback()
            raise

    @classmethod
    async def get_active_super_admin_user_ids(
        cls,
        *,
        session: AsyncSession,
    ) -> list[str]:
        result = await session.execute(
            select(Users.user_id)
            .join(Users.roles)
            .where(
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
                Role.role_code == "ROLE_SUPER_ADMIN",
            )
        )
        return [str(user_id) for user_id in result.scalars().all()]

    @classmethod
    async def create_notifications_bulk(
        cls,
        *,
        session: AsyncSession,
        notifications: list[Notification],
        commit: bool = False,
    ) -> int:
        if not notifications:
            return 0
        try:
            session.add_all(notifications)
            if commit:
                await session.commit()
            elif hasattr(session, "flush"):
                await session.flush()
            return len(notifications)
        except IntegrityError:
            if commit:
                await session.rollback()
            raise
        except Exception:
            if commit:
                await session.rollback()
            raise

    @classmethod
    async def exists_notification(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        notification_type: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> bool:
        """
        Returns True if a notification already exists for this recipient
        referencing the same entity (e.g. the same job). Used to keep
        notification dispatch idempotent even if the caller is invoked
        more than once for the same event.
        """

        result = await session.execute(
            select(Notification.notification_id)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.notification_type == notification_type,
                Notification.reference_type == reference_type,
                Notification.reference_id == reference_id,
            )
            .limit(1)
        )

        return result.scalar_one_or_none() is not None

    @classmethod
    async def get_latest_notification(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        notification_type: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> Notification | None:
        """
        Returns the most recently created notification matching this
        recipient/type/reference combination, if any. Used to derive
        cooldown windows (e.g. "one nudge per N hours") without needing
        a dedicated timestamp column on the source entity.
        """

        result = await session.execute(
            select(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.notification_type == notification_type,
                Notification.reference_type == reference_type,
                Notification.reference_id == reference_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none()

    @classmethod
    async def get_latest_notifications_for_references(
        cls,
        *,
        session: AsyncSession,
        notification_type: str,
        reference_type: str | None,
        reference_ids: list[str],
    ) -> dict[str, datetime]:
        """
        Batched version of get_latest_notification: returns
        {reference_id: latest_created_at} for every reference_id that has
        at least one matching notification. Avoids N+1 queries when
        rendering a list of entities that each need their own "last
        notified at" timestamp (e.g. an applications list).
        """

        if not reference_ids:
            return {}

        result = await session.execute(
            select(
                Notification.reference_id,
                func.max(Notification.created_at),
            )
            .where(
                Notification.notification_type == notification_type,
                Notification.reference_type == reference_type,
                Notification.reference_id.in_(reference_ids),
            )
            .group_by(Notification.reference_id)
        )

        return {row[0]: row[1] for row in result.all()}

    @classmethod
    async def get_notifications(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        page: int | None = None,
        page_size: int | None = None,
        is_read: bool | None = None,
        notification_type: str | None = None,
        notification_types: list[str] | None = None,
        category_types: list[str] | None = None,
        date_range: NormalizedDateRange | None = None,
        search: str | None = None,
        sort_order: str = "desc",
    ) -> list[Notification]:
        """
        Returns all notifications for a recipient,
        newest first.
        """

        query = (
            select(Notification)
            .where(cls._recipient_filter(recipient_id))
        )
        query = cls._apply_list_filters(
            query=query,
            is_read=is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            category_types=category_types,
            date_range=date_range,
            search=search,
        )
        order_by = Notification.created_at.asc() if sort_order.lower() == "asc" else Notification.created_at.desc()
        query = query.order_by(order_by)
        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)

        return list(result.scalars().all())

    @staticmethod
    def _apply_list_filters(
        *,
        query,
        is_read: bool | None,
        notification_type: str | None,
        notification_types: list[str] | None,
        category_types: list[str] | None,
        date_range: NormalizedDateRange | None,
        search: str | None,
    ):
        if is_read is not None:
            query = query.where(Notification.is_read.is_(is_read))
        if notification_type:
            query = query.where(Notification.notification_type == notification_type.upper())
        type_filters: set[str] = set()
        if notification_types:
            type_filters.update(value.upper() for value in notification_types if value)
        if category_types:
            type_filters.update(value.upper() for value in category_types if value)
        if type_filters:
            query = query.where(Notification.notification_type.in_(sorted(type_filters)))
        if date_range:
            start_at = normalize_datetime_for_db(date_range.utc_start)
            end_at = normalize_datetime_for_db(date_range.utc_end_exclusive)
            query = query.where(
                Notification.created_at >= start_at,
                Notification.created_at < end_at,
            )
        if search:
            term = f"%{search}%"
            query = query.where(
                or_(
                    Notification.title.ilike(term),
                    Notification.message.ilike(term),
                    Notification.notification_type.ilike(term),
                    Notification.reference_type.ilike(term),
                    Notification.reference_id.ilike(term),
                    Notification.entity_type.ilike(term),
                    Notification.entity_id.ilike(term),
                )
            )
        return query

    @classmethod
    async def count_notifications(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        is_read: bool | None = None,
        notification_type: str | None = None,
        notification_types: list[str] | None = None,
        category_types: list[str] | None = None,
        date_range: NormalizedDateRange | None = None,
        search: str | None = None,
    ) -> int:
        query = select(func.count(Notification.notification_id)).where(
            cls._recipient_filter(recipient_id)
        )
        query = cls._apply_list_filters(
            query=query,
            is_read=is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            category_types=category_types,
            date_range=date_range,
            search=search,
        )
        return await session.scalar(query) or 0

    @classmethod
    async def count_summary(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        today_start: datetime,
        today_end: datetime,
        high_priority_types: list[str],
    ) -> dict[str, int]:
        high_priority_types = [value.upper() for value in high_priority_types]
        result = await session.execute(
            select(
                func.count(Notification.notification_id).label("total_notifications"),
                func.coalesce(
                    func.sum(
                        case(
                            [(Notification.is_read.is_(False), 1)],
                            else_=0,
                        )
                    ),
                    0,
                ).label("unread_notifications"),
                func.coalesce(
                    func.sum(
                        case(
                            [
                                (
                                    and_(
                                        Notification.created_at >= today_start,
                                        Notification.created_at < today_end,
                                    ),
                                    1,
                                )
                            ],
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_notifications"),
                func.coalesce(
                    func.sum(
                        case(
                            [
                                (
                                    Notification.notification_type.in_(
                                        high_priority_types
                                    ),
                                    1,
                                )
                            ],
                            else_=0,
                        )
                    ),
                    0,
                ).label("high_priority_notifications"),
            ).where(cls._recipient_filter(recipient_id))
        )
        row = result.one()
        return {
            "total_notifications": int(row.total_notifications or 0),
            "unread_notifications": int(row.unread_notifications or 0),
            "today_notifications": int(row.today_notifications or 0),
            "high_priority_notifications": int(
                row.high_priority_notifications or 0
            ),
        }

    @classmethod
    async def unread_count(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        return await cls.count_notifications(
            session=session,
            recipient_id=recipient_id,
            is_read=False,
        )

    @classmethod
    async def get_notification(
        cls,
        *,
        session: AsyncSession,
        notification_id: str,
        recipient_id: str | None = None,
    ) -> Notification | None:
        """
        Returns a single notification by ID.
        """

        query = select(Notification).where(Notification.notification_id == notification_id)
        if recipient_id is not None:
            query = query.where(
                cls._recipient_filter(recipient_id)
            )
        result = await session.execute(query)

        return result.scalar_one_or_none()

    @classmethod
    async def mark_as_read(
        cls,
        *,
        session: AsyncSession,
        notification_id: str,
        recipient_id: str,
    ) -> bool:
        """
        Marks a single notification as read.
        """

        try:
            now = utc_now_naive()
            result = await session.execute(
                update(Notification)
                .where(
                    Notification.notification_id == notification_id,
                    cls._recipient_filter(recipient_id),
                    Notification.is_read.is_(False),
                )
                .values(
                    is_read=True,
                    read_at=now,
                    updated_at=now,
                )
                .returning(Notification.notification_id)
            )

            await session.commit()

            if result.scalar_one_or_none() is not None:
                return True
            return await cls.get_notification(
                session=session,
                notification_id=notification_id,
                recipient_id=recipient_id,
            ) is not None

        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def mark_all_as_read(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        """
        Marks all unread notifications as read.
        Returns the number of notifications updated.
        """

        try:
            result = await session.execute(
                update(Notification)
                .where(
                    or_(
                        Notification.recipient_user_id == recipient_id,
                        Notification.recipient_id == recipient_id,
                    ),
                    Notification.is_read.is_(False),
                )
                .values(
                    is_read=True,
                    read_at=utc_now_naive(),
                    updated_at=utc_now_naive(),
                )
            )

            await session.commit()

            return result.rowcount or 0

        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def mark_many_as_read(
        cls,
        *,
        session: AsyncSession,
        notification_ids: list[str],
        recipient_id: str,
    ) -> int:
        if not notification_ids:
            return 0
        try:
            now = utc_now_naive()
            result = await session.execute(
                update(Notification)
                .where(
                    Notification.notification_id.in_(notification_ids),
                    cls._recipient_filter(recipient_id),
                    Notification.is_read.is_(False),
                )
                .values(is_read=True, read_at=now, updated_at=now)
            )
            await session.commit()
            return result.rowcount or 0
        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def delete_notification(
        cls,
        *,
        session: AsyncSession,
        notification_id: str,
        recipient_id: str | None = None,
    ) -> bool:
        """
        Deletes a notification.
        """

        notification = await cls.get_notification(
            session=session,
            notification_id=notification_id,
            recipient_id=recipient_id,
        )

        if notification is None:
            return False

        try:
            await session.delete(notification)
            await session.commit()

            return True

        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def clear_read_for_user(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        try:
            result = await session.execute(
                delete(Notification).where(
                    cls._recipient_filter(recipient_id),
                    Notification.is_read.is_(True),
                )
            )
            await session.commit()
            return result.rowcount or 0
        except Exception:
            await session.rollback()
            raise

    @classmethod
    async def delete_many(
        cls,
        *,
        session: AsyncSession,
        notification_ids: list[str],
        recipient_id: str,
    ) -> int:
        if not notification_ids:
            return 0
        try:
            result = await session.execute(
                delete(Notification).where(
                    Notification.notification_id.in_(notification_ids),
                    cls._recipient_filter(recipient_id),
                )
            )
            await session.commit()
            return result.rowcount or 0
        except Exception:
            await session.rollback()
            raise
