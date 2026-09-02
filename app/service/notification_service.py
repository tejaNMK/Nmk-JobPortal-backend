import logging
from datetime import date, datetime, time, timedelta, timezone
from app.utils.utc import utc_now_naive

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.notification import Notification
from app.repository.notification_repo import NotificationRepo
from app.schema.notification import NotificationResponseSchema
from app.utils.date_range import NormalizedDateRange

logger = logging.getLogger(__name__)


APPLICATION_TYPES = {
    "APPLICATION_RECEIVED",
    "APPLICATION_WITHDRAWN",
    "APPLICATION_SHORTLISTED",
    "APPLICATION_REJECTED",
    "APPLICATION_HIRED",
    "APPLICATION_STATUS",
    "APPLICATION_NUDGE",
    "SHORTLIST",
}
JOB_TYPES = {
    "JOB_PUBLISHED",
    "JOB_POSTED",
    "JOB_CLOSED",
    "JOB_EXPIRED",
    "JOB_EDITED",
    "JOB_APPROVAL",
    "JOB_ALERT",
}
INTERVIEW_TYPES = {
    "INTERVIEW",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_RESCHEDULED",
    "INTERVIEW_CANCELLED",
    "INTERVIEW_REMINDER",
    "INTERVIEW_COMPLETED",
    "CANDIDATE_ACCEPTED_INTERVIEW",
    "CANDIDATE_DECLINED_INTERVIEW",
    "INVITATION_ACCEPTED",
    "INVITATION_REJECTED",
}
SUBSCRIPTION_TYPES = {
    "PACKAGE_PURCHASED",
    "PACKAGE_EXPIRING",
    "CREDITS_LOW",
    "SUBSCRIPTION_EXPIRING",
    "SUBSCRIPTION_RENEWED",
    "SUBSCRIPTION_SELF_SUBSCRIBED",
    "SUBSCRIPTION_ASSIGNED",
    "SUBSCRIPTION_CREATED",
    "SUBSCRIPTION_UPDATED",
}
SYSTEM_TYPES = {
    "EMPLOYER_PROFILE_APPROVED",
    "EMPLOYER_VERIFICATION",
    "RESUME_DOWNLOADED",
    "SUPPORT_TICKET_UPDATED",
    "EMAIL_VERIFICATION",
    "MOBILE_VERIFICATION",
}
ANNOUNCEMENT_TYPES = {
    "SYSTEM_ANNOUNCEMENT",
    "ADMIN_ANNOUNCEMENT",
}

CATEGORY_TYPES = {
    "APPLICATIONS": APPLICATION_TYPES,
    "JOBS": JOB_TYPES,
    "INTERVIEWS": INTERVIEW_TYPES,
    "SUBSCRIPTION": SUBSCRIPTION_TYPES,
    "SYSTEM": SYSTEM_TYPES,
    "ANNOUNCEMENTS": ANNOUNCEMENT_TYPES,
}

HIGH_PRIORITY_TYPES = {
    "JOB_EXPIRED",
    "JOB_APPROVAL",
    "APPLICATION_RECEIVED",
    "APPLICATION_WITHDRAWN",
    "INTERVIEW_CANCELLED",
    "INTERVIEW_REMINDER",
    "PACKAGE_EXPIRING",
    "CREDITS_LOW",
    "SUBSCRIPTION_EXPIRING",
    "EMPLOYER_VERIFICATION",
    "SUPPORT_TICKET_UPDATED",
}

MEDIUM_PRIORITY_TYPES = {
    "JOB_PUBLISHED",
    "JOB_POSTED",
    "JOB_CLOSED",
    "JOB_EDITED",
    "APPLICATION_SHORTLISTED",
    "APPLICATION_REJECTED",
    "APPLICATION_HIRED",
    "INTERVIEW",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_RESCHEDULED",
    "INTERVIEW_COMPLETED",
    "CANDIDATE_ACCEPTED_INTERVIEW",
    "CANDIDATE_DECLINED_INTERVIEW",
    "PACKAGE_PURCHASED",
    "SUBSCRIPTION_RENEWED",
    "EMPLOYER_PROFILE_APPROVED",
}

TYPE_PRESENTATION = {
    "APPLICATIONS": ("user-check", "#2563eb"),
    "JOBS": ("briefcase-business", "#0f766e"),
    "INTERVIEWS": ("calendar-clock", "#7c3aed"),
    "SUBSCRIPTION": ("credit-card", "#b45309"),
    "ANNOUNCEMENTS": ("megaphone", "#be123c"),
    "SYSTEM": ("shield-check", "#475569"),
}

ACTION_BUTTONS = {
    "APPLICATIONS": "View application",
    "JOBS": "View job",
    "INTERVIEWS": "View interview",
    "SUBSCRIPTION": "View subscription",
    "ANNOUNCEMENTS": "View announcement",
    "SYSTEM": "View details",
}


class NotificationService:
    """
    Generic notification service.

    This service is reusable across the application and can support:
    - Job Alerts
    - Interview Notifications
    - Shortlisted Candidates
    - Application Status Updates
    - Candidate Invitations
    - Email/Mobile Verification
    """

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
    ) -> Notification | None:
        """
        Creates an in-app notification.

        Failures are logged but never propagated so they do not
        interrupt the caller's business workflow.
        """

        try:
            return await NotificationRepo.create_notification(
                session=session,
                recipient_id=recipient_id,
                title=title,
                message=message,
                notification_type=notification_type,
                reference_type=reference_type,
                reference_id=reference_id,
                recipient_role=recipient_role,
                entity_type=entity_type,
                entity_id=entity_id,
                target_route=target_route,
                metadata=metadata,
                event_key=event_key,
                commit=commit,
            )

        except IntegrityError:
            logger.info(
                "Skipping duplicate notification.",
                extra={
                    "recipient_id": recipient_id,
                    "notification_type": notification_type,
                    "event_key": event_key,
                },
            )
            return None
        except Exception:
            logger.exception(
                "Failed to create notification.",
                extra={
                    "recipient_id": recipient_id,
                    "notification_type": notification_type,
                    "reference_type": reference_type,
                    "reference_id": reference_id,
                },
            )
            return None

    @classmethod
    async def create_for_super_admins(
        cls,
        session: AsyncSession,
        *,
        notification_type: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        target_route: str | None = None,
        metadata: dict | None = None,
        event_key: str | None = None,
        commit: bool = False,
    ) -> int:
        try:
            recipient_ids = await NotificationRepo.get_active_super_admin_user_ids(
                session=session,
            )
            now = utc_now_naive()
            notifications = [
                Notification(
                    recipient_id=recipient_id,
                    recipient_user_id=recipient_id,
                    recipient_role="ROLE_SUPER_ADMIN",
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    reference_type=entity_type,
                    reference_id=entity_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    target_route=target_route,
                    metadata_=metadata,
                    event_key=event_key,
                    is_read=False,
                    read_at=None,
                    created_at=now,
                    updated_at=now,
                )
                for recipient_id in recipient_ids
            ]
            return await NotificationRepo.create_notifications_bulk(
                session=session,
                notifications=notifications,
                commit=commit,
            )
        except IntegrityError:
            logger.info(
                "Skipping duplicate Super Admin notification.",
                extra={"notification_type": notification_type, "event_key": event_key},
            )
            return 0
        except Exception:
            logger.exception(
                "Failed to create Super Admin notification.",
                extra={"notification_type": notification_type, "event_key": event_key},
            )
            return 0

    @classmethod
    async def notification_already_sent(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        notification_type: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> bool:
        """
        Checks whether a matching notification was already created, so
        callers can avoid dispatching duplicates for the same event.
        """

        return await NotificationRepo.exists_notification(
            session=session,
            recipient_id=recipient_id,
            notification_type=notification_type,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    @classmethod
    async def get_latest_notification(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
        notification_type: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> Notification | None:
        """
        Returns the most recent notification for this recipient/type/
        reference combination, or None. Used for cooldown checks.
        """

        return await NotificationRepo.get_latest_notification(
            session=session,
            recipient_id=recipient_id,
            notification_type=notification_type,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    @classmethod
    async def get_latest_notifications_for_references(
        cls,
        *,
        session: AsyncSession,
        notification_type: str,
        reference_type: str | None,
        reference_ids: list[str],
    ):
        """
        Batched {reference_id: latest_created_at} lookup — see
        NotificationRepo.get_latest_notifications_for_references.
        """

        return await NotificationRepo.get_latest_notifications_for_references(
            session=session,
            notification_type=notification_type,
            reference_type=reference_type,
            reference_ids=reference_ids,
        )

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
        Returns all notifications for a recipient.
        """

        return await NotificationRepo.get_notifications(
            session=session,
            recipient_id=recipient_id,
            page=page,
            page_size=page_size,
            is_read=is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            category_types=category_types,
            date_range=date_range,
            search=search,
            sort_order=sort_order,
        )

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
        return await NotificationRepo.count_notifications(
            session=session,
            recipient_id=recipient_id,
            is_read=is_read,
            notification_type=notification_type,
            notification_types=notification_types,
            category_types=category_types,
            date_range=date_range,
            search=search,
        )

    @classmethod
    async def get_count_summary(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> dict[str, int]:
        today = date.today()
        today_start = datetime.combine(today, time.min)
        today_end = today_start + timedelta(days=1)
        return await NotificationRepo.count_summary(
            session=session,
            recipient_id=recipient_id,
            today_start=today_start,
            today_end=today_end,
            high_priority_types=sorted(HIGH_PRIORITY_TYPES),
        )

    @classmethod
    def get_types_for_category(cls, category: str | None) -> list[str] | None:
        if not category:
            return None
        normalized = category.strip().upper().replace(" ", "_")
        if normalized == "APPLICATION":
            normalized = "APPLICATIONS"
        if normalized == "JOB":
            normalized = "JOBS"
        if normalized == "INTERVIEW":
            normalized = "INTERVIEWS"
        if normalized == "ANNOUNCEMENT":
            normalized = "ANNOUNCEMENTS"
        values = CATEGORY_TYPES.get(normalized)
        return sorted(values) if values else None

    @classmethod
    def get_types_for_priority(cls, priority: str | None) -> list[str] | None:
        if not priority:
            return None
        normalized = priority.strip().upper()
        if normalized == "HIGH":
            return sorted(HIGH_PRIORITY_TYPES)
        if normalized == "MEDIUM":
            return sorted(MEDIUM_PRIORITY_TYPES)
        if normalized == "LOW":
            known = set().union(*CATEGORY_TYPES.values())
            return sorted(known - HIGH_PRIORITY_TYPES - MEDIUM_PRIORITY_TYPES)
        return None

    @classmethod
    def format_notification(cls, notification: Notification) -> dict:
        base = NotificationResponseSchema.model_validate(notification).model_dump()
        notification_type = (
            base.get("notification_type")
            or getattr(notification, "notification_type", "")
            or ""
        ).upper()
        metadata = base.get("metadata") or {}
        category = cls._category_for_type(notification_type)
        priority = cls._priority_for_type(notification_type, metadata)
        icon, color = TYPE_PRESENTATION.get(
            category,
            TYPE_PRESENTATION["SYSTEM"],
        )
        target_route = base.get("target_route")
        entity_type = base.get("entity_type") or base.get("reference_type")
        entity_id = base.get("entity_id") or base.get("reference_id")
        description = metadata.get("description") or base.get("message")

        base.update(
            {
                "type": notification_type,
                "description": description,
                "priority": priority,
                "category": category,
                "icon": metadata.get("icon") or icon,
                "color": metadata.get("color") or color,
                "redirect_url": metadata.get("redirect_url") or target_route,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "relative_time": cls._relative_time(base.get("created_at")),
                "action_required": bool(
                    metadata.get("action_required")
                    or notification_type in HIGH_PRIORITY_TYPES
                ),
                "action_button": metadata.get("action_button")
                or ACTION_BUTTONS.get(category),
                "metadata": metadata,
            }
        )
        return base

    @classmethod
    def format_notifications(cls, notifications: list[Notification]) -> list[dict]:
        return [cls.format_notification(notification) for notification in notifications]

    @staticmethod
    def _category_for_type(notification_type: str) -> str:
        for category, notification_types in CATEGORY_TYPES.items():
            if notification_type in notification_types:
                return category
        return "SYSTEM"

    @staticmethod
    def _priority_for_type(notification_type: str, metadata: dict) -> str:
        metadata_priority = metadata.get("priority")
        if metadata_priority:
            return str(metadata_priority).upper()
        if notification_type in HIGH_PRIORITY_TYPES:
            return "HIGH"
        if notification_type in MEDIUM_PRIORITY_TYPES:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _relative_time(created_at) -> str | None:
        if created_at is None:
            return None
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                return None
        now = utc_now_naive()
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
        seconds = max(int((now - created_at).total_seconds()), 0)
        if seconds < 60:
            return "Just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        if days == 1:
            return "Yesterday"
        return f"{days} days ago"

    @classmethod
    async def get_unread_count(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        return await NotificationRepo.unread_count(
            session=session,
            recipient_id=recipient_id,
        )

    @classmethod
    async def get_notification(
        cls,
        *,
        session: AsyncSession,
        notification_id: str,
    ) -> Notification | None:
        """
        Returns a single notification by ID.
        """

        return await NotificationRepo.get_notification(
            session=session,
            notification_id=notification_id,
        )

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

        return await NotificationRepo.mark_as_read(
            session=session,
            notification_id=notification_id,
            recipient_id=recipient_id,
        )

    @classmethod
    async def mark_all_as_read(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        """
        Marks all notifications as read.
        """

        return await NotificationRepo.mark_all_as_read(
            session=session,
            recipient_id=recipient_id,
        )

    @classmethod
    async def mark_many_as_read(
        cls,
        *,
        session: AsyncSession,
        notification_ids: list[str],
        recipient_id: str,
    ) -> int:
        return await NotificationRepo.mark_many_as_read(
            session=session,
            notification_ids=list(dict.fromkeys(notification_ids)),
            recipient_id=recipient_id,
        )

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

        return await NotificationRepo.delete_notification(
            session=session,
            notification_id=notification_id,
            recipient_id=recipient_id,
        )

    @classmethod
    async def clear_read_for_user(
        cls,
        *,
        session: AsyncSession,
        recipient_id: str,
    ) -> int:
        return await NotificationRepo.clear_read_for_user(
            session=session,
            recipient_id=recipient_id,
        )

    @classmethod
    async def delete_many(
        cls,
        *,
        session: AsyncSession,
        notification_ids: list[str],
        recipient_id: str,
    ) -> int:
        return await NotificationRepo.delete_many(
            session=session,
            notification_ids=list(dict.fromkeys(notification_ids)),
            recipient_id=recipient_id,
        )
