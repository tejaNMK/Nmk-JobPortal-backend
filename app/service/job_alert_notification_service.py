import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from dateutil import tz
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    JOB_ALERT_DAILY_HOUR,
    JOB_ALERT_DAILY_MINUTE,
    JOB_ALERT_DEFAULT_TIMEZONE,
    JOB_ALERT_WEEKLY_DAY,
    JOB_ALERT_WEEKLY_HOUR,
    JOB_ALERT_WEEKLY_MINUTE,
)
from app.constants.notification_constants import (
    NotificationChannel,
    NotificationFrequency,
    NotificationPreference,
    NotificationTitle,
    NotificationType,
    ReferenceType,
)
from app.model.employer_model.job import Job
from app.repository.candidate_repo import CandidateProfileRepo
from app.repository.job_alert_notification_delivery_repo import (
    JobAlertNotificationDeliveryRepo,
)
from app.service.authentication.email_service import EmailService
from app.service.notification_service import NotificationService
from app.service.subscription.subscription_validator import SubscriptionValidator

logger = logging.getLogger(__name__)

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class JobAlertNotificationService:
    """
    Sends Job Alert notifications to candidates whose active alerts match jobs.
    Instant, daily, and weekly flows all use _is_match for alert criteria.
    """

    _EXPERIENCE_LEVEL_RANGES = {
        "FRESHER": (0, 0),
        "JUNIOR": (1, 3),
        "MID_LEVEL": (3, 5),
        "SENIOR": (5, None),
    }

    @classmethod
    async def notify_matching_candidates(
        cls,
        *,
        session: AsyncSession,
        job: Job,
    ) -> None:
        """
        Fetch active alerts, evaluate matches and send notifications.

        This method must NEVER raise an exception back to JobService.
        """
        try:
            alerts = await CandidateProfileRepo.get_active_job_alert_candidates(
                session=session
            )
            if not alerts:
                logger.info("No active job alerts found.", extra={"job_id": job.job_id})
                return

            matched_count = 0
            notified_delivery_keys = set()

            for alert in alerts:
                try:
                    if not await cls._candidate_has_job_alerts_feature(
                        session=session,
                        alert=alert,
                    ):
                        continue
                    if not cls._is_match(job, alert):
                        continue
                    matched_count += 1

                    frequency = cls._normalize_frequency(alert.frequency)
                    if frequency != NotificationFrequency.INSTANT:
                        continue

                    delivery_guard_keys = cls._instant_delivery_guard_keys(alert)
                    if delivery_guard_keys.issubset(notified_delivery_keys):
                        logger.info(
                            "Skipping duplicate job alert notification; "
                            "alert channel already processed for this job.",
                            extra={
                                "job_id": job.job_id,
                                "candidate_id": alert.candidate_id,
                                "alert_id": alert.alert_id,
                                "delivery_guard_keys": sorted(delivery_guard_keys),
                            },
                        )
                        continue
                    notified_delivery_keys.update(delivery_guard_keys)

                    await cls._dispatch_notification(
                        session=session,
                        alert=alert,
                        job=job,
                        candidate_name=cls._candidate_name(
                            alert.first_name,
                            alert.last_name,
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Failed to send job alert notification.",
                        extra={
                            "job_id": job.job_id,
                            "candidate_id": getattr(alert, "candidate_id", None),
                            "alert_id": getattr(alert, "alert_id", None),
                        },
                    )

            if matched_count == 0:
                logger.info("No matching job alerts found.", extra={"job_id": job.job_id})

        except Exception:
            logger.exception(
                "Job alert notification workflow failed.",
                extra={"job_id": job.job_id},
            )

    @classmethod
    async def _dispatch_notification(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        job: Job,
        candidate_name: str,
    ) -> None:
        """
        Dispatch instant notifications based on notification preference.
        Daily and weekly notifications are handled by scheduled jobs.
        """
        try:
            frequency = cls._normalize_frequency(alert.frequency)
            if frequency != NotificationFrequency.INSTANT:
                return

            preference = cls._normalize_preference(alert.notification_preference)
            send_email, create_in_app = cls._delivery_channels(preference)

            if send_email:
                await cls._send_instant_email(
                    session=session,
                    alert=alert,
                    job=job,
                    candidate_name=candidate_name,
                )

            if create_in_app:
                await cls._create_instant_in_app_notification(
                    session=session,
                    alert=alert,
                    job=job,
                )

            logger.info(
                "Job alert notification processed.",
                extra={
                    "job_id": job.job_id,
                    "candidate_id": alert.candidate_id,
                    "alert_id": alert.alert_id,
                    "preference": preference,
                    "frequency": frequency,
                },
            )
        except Exception:
            logger.exception(
                "Notification dispatch failed.",
                extra={
                    "job_id": job.job_id,
                    "candidate_id": getattr(alert, "candidate_id", None),
                    "alert_id": getattr(alert, "alert_id", None),
                },
            )

    @classmethod
    async def process_daily_notifications(
        cls,
        *,
        session: AsyncSession,
        run_at: datetime | None = None,
    ) -> None:
        run_at = run_at or datetime.now()
        window_start, window_end = cls._daily_window(run_at)
        await cls._process_digest_notifications(
            session=session,
            frequency=NotificationFrequency.DAILY,
            window_start=window_start,
            window_end=window_end,
        )

    @classmethod
    async def process_weekly_notifications(
        cls,
        *,
        session: AsyncSession,
        run_at: datetime | None = None,
    ) -> None:
        run_at = run_at or datetime.now()
        window_start, window_end = cls._weekly_window(run_at)
        await cls._process_digest_notifications(
            session=session,
            frequency=NotificationFrequency.WEEKLY,
            window_start=window_start,
            window_end=window_end,
        )

    @classmethod
    async def process_due_notifications(
        cls,
        *,
        session: AsyncSession,
        run_at_utc: datetime | None = None,
        previous_run_at_utc: datetime | None = None,
    ) -> None:
        run_at_utc = cls._as_utc(run_at_utc or datetime.now(UTC))
        previous_run_at_utc = (
            cls._as_utc(previous_run_at_utc)
            if previous_run_at_utc is not None
            else None
        )
        if previous_run_at_utc is not None and previous_run_at_utc >= run_at_utc:
            previous_run_at_utc = None

        await cls._process_due_digest_notifications(
            session=session,
            frequency=NotificationFrequency.DAILY,
            run_at_utc=run_at_utc,
            previous_run_at_utc=previous_run_at_utc,
        )
        await cls._process_due_digest_notifications(
            session=session,
            frequency=NotificationFrequency.WEEKLY,
            run_at_utc=run_at_utc,
            previous_run_at_utc=previous_run_at_utc,
        )

    @classmethod
    async def _process_due_digest_notifications(
        cls,
        *,
        session: AsyncSession,
        frequency: str,
        run_at_utc: datetime,
        previous_run_at_utc: datetime | None,
    ) -> None:
        try:
            alerts = await CandidateProfileRepo.get_active_job_alert_candidates_by_frequency(
                session=session,
                frequency=frequency,
            )
            if not alerts:
                return

            for alert in alerts:
                if not await cls._candidate_has_job_alerts_feature(
                    session=session,
                    alert=alert,
                ):
                    continue
                timezone_name = cls._resolve_timezone_name(alert)
                timezone = cls._load_timezone(timezone_name)
                local_run_at = run_at_utc.astimezone(timezone)
                local_previous_run_at = (
                    previous_run_at_utc.astimezone(timezone)
                    if previous_run_at_utc is not None
                    else None
                )

                window = cls._due_digest_window_utc(
                    frequency=frequency,
                    local_run_at=local_run_at,
                    local_previous_run_at=local_previous_run_at,
                )
                if window is None:
                    continue

                window_start, window_end = window
                jobs = await CandidateProfileRepo.get_jobs_posted_between(
                    session=session,
                    start_at=window_start,
                    end_at=window_end,
                )
                matched_jobs = [
                    job
                    for job in jobs
                    if cls._is_match(job, alert)
                ]
                if not matched_jobs:
                    continue

                recipient_id = str(alert.user_id)
                reference_id = cls._digest_reference_id(
                    frequency=frequency,
                    window_start=window_start,
                    window_end=window_end,
                    recipient_id=recipient_id,
                    alert_id=alert.alert_id,
                )
                await cls._dispatch_digest_notification(
                    session=session,
                    alert=alert,
                    jobs=matched_jobs,
                    candidate_name=cls._candidate_name(
                        alert.first_name,
                        alert.last_name,
                    ),
                    frequency=frequency,
                    recipient_id=recipient_id,
                    reference_id=reference_id,
                    window_start=window_start,
                    window_end=window_end,
                )
        except Exception:
            logger.exception(
                "Due Job Alert digest workflow failed.",
                extra={
                    "frequency": frequency,
                    "run_at_utc": run_at_utc,
                    "previous_run_at_utc": previous_run_at_utc,
                },
            )

    @classmethod
    async def _process_digest_notifications(
        cls,
        *,
        session: AsyncSession,
        frequency: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        try:
            alerts = await CandidateProfileRepo.get_active_job_alert_candidates_by_frequency(
                session=session,
                frequency=frequency,
            )
            if not alerts:
                return

            jobs = await CandidateProfileRepo.get_jobs_posted_between(
                session=session,
                start_at=window_start,
                end_at=window_end,
            )
            if not jobs:
                return

            grouped = defaultdict(lambda: {"alert": None, "jobs": {}})
            for alert in alerts:
                if not await cls._candidate_has_job_alerts_feature(
                    session=session,
                    alert=alert,
                ):
                    continue
                for job in jobs:
                    if not cls._is_match(job, alert):
                        continue
                    bucket = grouped[str(alert.user_id)]
                    bucket["alert"] = bucket["alert"] or alert
                    bucket["jobs"][job.job_id] = job

            for recipient_id, payload in grouped.items():
                alert = payload["alert"]
                matched_jobs = list(payload["jobs"].values())
                if not alert or not matched_jobs:
                    continue

                reference_id = cls._digest_reference_id(
                    frequency=frequency,
                    window_start=window_start,
                    window_end=window_end,
                    recipient_id=recipient_id,
                    alert_id=getattr(alert, "alert_id", None),
                )
                await cls._dispatch_digest_notification(
                    session=session,
                    alert=alert,
                    jobs=matched_jobs,
                    candidate_name=cls._candidate_name(
                        alert.first_name,
                        alert.last_name,
                    ),
                    frequency=frequency,
                    recipient_id=recipient_id,
                    reference_id=reference_id,
                    window_start=window_start,
                    window_end=window_end,
                )
        except Exception:
            logger.exception(
                "Job alert digest workflow failed.",
                extra={
                    "frequency": frequency,
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )

    @classmethod
    async def _dispatch_digest_notification(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        jobs: list[Any],
        candidate_name: str,
        frequency: str,
        recipient_id: str,
        reference_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        preference = cls._normalize_preference(alert.notification_preference)
        send_email, create_in_app = cls._delivery_channels(preference)

        if send_email:
            await cls._send_digest_email(
                session=session,
                alert=alert,
                jobs=jobs,
                candidate_name=candidate_name,
                frequency=frequency,
                recipient_id=recipient_id,
                window_start=window_start,
                window_end=window_end,
            )

        if create_in_app:
            await cls._create_digest_in_app_notification(
                session=session,
                alert=alert,
                jobs=jobs,
                frequency=frequency,
                recipient_id=recipient_id,
                reference_id=reference_id,
                window_start=window_start,
                window_end=window_end,
            )

    @classmethod
    def _experience_level_range(cls, experience_level: Any) -> tuple[int, int | None] | None:
        normalized = str(experience_level or "").strip().upper()
        return cls._EXPERIENCE_LEVEL_RANGES.get(normalized)

    @staticmethod
    def _experience_ranges_overlap(
        alert_min: int,
        alert_max: int | None,
        job_min: int | None,
        job_max: int | None,
    ) -> bool:
        normalized_job_min = job_min if job_min is not None else 0

        if alert_max is None and job_max is None:
            return True
        if alert_max is None:
            return job_max >= alert_min
        if job_max is None:
            return normalized_job_min <= alert_max
        return normalized_job_min <= alert_max and job_max >= alert_min

    @classmethod
    def _is_match(cls, job: Job, alert: Any) -> bool:
        """
        Returns True when any populated alert criteria match the job.
        Empty alert fields are ignored. An alert with no populated matching
        criteria matches all newly posted jobs.
        """
        matches = []

        title_matches = None
        if getattr(alert, "job_title", None) and alert.job_title.strip():
            title_matches = (
                alert.job_title.strip().lower() in (job.title or "").strip().lower()
            )
            matches.append(title_matches)

        if getattr(alert, "job_category", None) and alert.job_category.strip():
            matches.append(cls._equals(job.job_category, alert.job_category))

        if alert.preferred_location and alert.preferred_location.strip():
            matches.append(
                alert.preferred_location.strip().lower()
                in (job.location or "").strip().lower()
            )

        if getattr(alert, "experience_level", None):
            alert_experience_range = cls._experience_level_range(alert.experience_level)
            if alert_experience_range is not None:
                alert_min, alert_max = alert_experience_range
                matches.append(
                    cls._experience_ranges_overlap(
                        alert_min,
                        alert_max,
                        job.experience_min,
                        job.experience_max,
                    )
                )

        if alert.employment_type:
            matches.append(cls._equals(job.employment_type, alert.employment_type))

        return any(matches) if matches else True

    @classmethod
    async def _candidate_has_job_alerts_feature(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
    ) -> bool:
        user_id = getattr(alert, "user_id", None)
        if not user_id:
            return False
        if session is None:
            return True
        try:
            await SubscriptionValidator(
                session=session,
                user_id=user_id,
                role="CANDIDATE",
            ).require_feature("job_alerts")
            return True
        except Exception:
            logger.info(
                "Skipping job alert notification; subscription does not allow job alerts.",
                extra={
                    "candidate_id": getattr(alert, "candidate_id", None),
                    "alert_id": getattr(alert, "alert_id", None),
                },
            )
            return False

    @classmethod
    async def _send_instant_email(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        job: Job,
        candidate_name: str,
    ) -> None:
        if not alert.email:
            return

        delivery = await cls._reserve_delivery(
            session=session,
            candidate_id=alert.candidate_id,
            recipient_id=str(alert.user_id),
            alert_id=alert.alert_id,
            job_id=job.job_id,
            frequency=NotificationFrequency.INSTANT,
            channel=NotificationChannel.EMAIL,
        )
        if delivery is None:
            return

        try:
            await EmailService.send_job_alert_email(
                to_email=alert.email,
                candidate_name=candidate_name,
                company_name=job.company_name,
                job_title=job.title,
                location=job.location,
                employment_type=job.employment_type,
                experience_required=(
                    f"{job.experience_min}-{job.experience_max}"
                    if job.experience_min is not None
                    and job.experience_max is not None
                    else "Not Specified"
                ),
                application_deadline=job.application_deadline,
            )
            await JobAlertNotificationDeliveryRepo.mark_sent(
                session=session,
                delivery_id=delivery.id,
            )
        except Exception as exc:
            await cls._mark_delivery_failed(
                session=session,
                delivery_id=delivery.id,
                exc=exc,
            )

    @classmethod
    async def _create_instant_in_app_notification(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        job: Job,
    ) -> None:
        delivery = await cls._reserve_delivery(
            session=session,
            candidate_id=alert.candidate_id,
            recipient_id=str(alert.user_id),
            alert_id=alert.alert_id,
            job_id=job.job_id,
            frequency=NotificationFrequency.INSTANT,
            channel=NotificationChannel.IN_APP,
        )
        if delivery is None:
            return

        try:
            message = (
                f"A new job '{job.title}' at "
                f"{job.company_name} matches your job alert."
            )
            notification = await NotificationService.create_notification(
                session=session,
                recipient_id=str(alert.user_id),
                recipient_role="ROLE_CANDIDATE",
                title=NotificationTitle.JOB_ALERT,
                message=message,
                notification_type=NotificationType.JOB_ALERT,
                reference_type=ReferenceType.JOB,
                reference_id=job.job_id,
                entity_type=ReferenceType.JOB,
                entity_id=job.job_id,
                target_route=f"/candidate/jobs/{job.job_id}",
                metadata={
                    "alert_id": alert.alert_id,
                    "job_id": job.job_id,
                    "job_title": job.title,
                    "company_name": job.company_name,
                },
                event_key=f"job_alert:instant:{alert.alert_id}:{job.job_id}",
            )
            if notification is None:
                raise RuntimeError("in-app notification creation failed")
            await JobAlertNotificationDeliveryRepo.mark_sent(
                session=session,
                delivery_id=delivery.id,
            )
        except Exception as exc:
            await cls._mark_delivery_failed(
                session=session,
                delivery_id=delivery.id,
                exc=exc,
            )

    @classmethod
    async def _send_digest_email(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        jobs: list[Any],
        candidate_name: str,
        frequency: str,
        recipient_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        if not alert.email:
            return

        delivery = await cls._reserve_delivery(
            session=session,
            candidate_id=alert.candidate_id,
            recipient_id=recipient_id,
            alert_id=alert.alert_id,
            job_id=None,
            frequency=frequency,
            channel=NotificationChannel.EMAIL,
            window_start=window_start,
            window_end=window_end,
        )
        if delivery is None:
            return

        try:
            await EmailService.send_job_alert_summary_email(
                to_email=alert.email,
                candidate_name=candidate_name,
                jobs=jobs,
            )
            await JobAlertNotificationDeliveryRepo.mark_sent(
                session=session,
                delivery_id=delivery.id,
            )
        except Exception as exc:
            await cls._mark_delivery_failed(
                session=session,
                delivery_id=delivery.id,
                exc=exc,
            )

    @classmethod
    async def _create_digest_in_app_notification(
        cls,
        *,
        session: AsyncSession,
        alert: Any,
        jobs: list[Any],
        frequency: str,
        recipient_id: str,
        reference_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        delivery = await cls._reserve_delivery(
            session=session,
            candidate_id=alert.candidate_id,
            recipient_id=recipient_id,
            alert_id=alert.alert_id,
            job_id=None,
            frequency=frequency,
            channel=NotificationChannel.IN_APP,
            window_start=window_start,
            window_end=window_end,
        )
        if delivery is None:
            return

        try:
            count = len(jobs)
            title = (
                NotificationTitle.DAILY_JOB_ALERT
                if frequency == NotificationFrequency.DAILY
                else NotificationTitle.WEEKLY_JOB_ALERT
            )
            notification = await NotificationService.create_notification(
                session=session,
                recipient_id=recipient_id,
                recipient_role="ROLE_CANDIDATE",
                title=title,
                message=f"{count} new jobs matched your Job Alert.",
                notification_type=NotificationType.JOB_ALERT,
                reference_type=ReferenceType.JOB,
                reference_id=reference_id,
                entity_type=ReferenceType.JOB,
                entity_id=reference_id,
                target_route="/candidate/job-alert",
                metadata={
                    "alert_id": alert.alert_id,
                    "frequency": frequency,
                    "matched_job_count": count,
                    "job_ids": [job.job_id for job in jobs],
                },
                event_key=f"job_alert:{frequency.lower()}:{reference_id}",
            )
            if notification is None:
                raise RuntimeError("in-app notification creation failed")
            await JobAlertNotificationDeliveryRepo.mark_sent(
                session=session,
                delivery_id=delivery.id,
            )
        except Exception as exc:
            await cls._mark_delivery_failed(
                session=session,
                delivery_id=delivery.id,
                exc=exc,
            )

    @classmethod
    async def _reserve_delivery(
        cls,
        *,
        session: AsyncSession,
        candidate_id: str | None,
        recipient_id: str,
        alert_id: str | None,
        job_id: str | None,
        frequency: str,
        channel: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ):
        delivery_key = cls._delivery_key(
            recipient_id=recipient_id,
            alert_id=alert_id,
            job_id=job_id,
            frequency=frequency,
            channel=channel,
            window_start=window_start,
            window_end=window_end,
        )
        delivery = await JobAlertNotificationDeliveryRepo.reserve_delivery(
            session=session,
            candidate_id=candidate_id,
            recipient_id=recipient_id,
            alert_id=alert_id,
            job_id=job_id,
            frequency=frequency,
            notification_type=NotificationType.JOB_ALERT,
            channel=channel,
            delivery_key=delivery_key,
            window_start=window_start,
            window_end=window_end,
        )
        if delivery is None:
            logger.info(
                "Skipping duplicate Job Alert delivery.",
                extra={
                    "delivery_key": delivery_key,
                    "recipient_id": recipient_id,
                    "alert_id": alert_id,
                    "job_id": job_id,
                    "frequency": frequency,
                    "channel": channel,
                },
            )
        return delivery

    @classmethod
    async def _mark_delivery_failed(
        cls,
        *,
        session: AsyncSession,
        delivery_id: str,
        exc: Exception,
    ) -> None:
        try:
            await JobAlertNotificationDeliveryRepo.mark_failed(
                session=session,
                delivery_id=delivery_id,
                error=cls._sanitize_error(exc),
            )
        except Exception:
            logger.exception(
                "Failed to mark Job Alert delivery as failed.",
                extra={"delivery_id": delivery_id},
            )

    @staticmethod
    def _delivery_key(
        *,
        recipient_id: str,
        alert_id: str | None,
        job_id: str | None,
        frequency: str,
        channel: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> str:
        if frequency == NotificationFrequency.INSTANT:
            return (
                f"JOB_ALERT:{NotificationFrequency.INSTANT}:"
                f"{recipient_id}:{alert_id}:{job_id}:"
                f"{NotificationType.JOB_ALERT}:{channel}"
            )

        return (
            f"JOB_ALERT:{frequency}:{recipient_id}:"
            f"{alert_id}:{window_start.isoformat()}:{window_end.isoformat()}:{channel}"
        )

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        message = str(exc) or exc.__class__.__name__
        sanitized = " ".join(message.split())
        for token in ("password", "secret", "token", "credential", "apikey", "api_key"):
            sanitized = sanitized.replace(token, "[redacted]")
            sanitized = sanitized.replace(token.upper(), "[redacted]")
        return sanitized[:300]

    @staticmethod
    def _normalize_preference(preference: str | None) -> str:
        normalized = NotificationPreference.normalize(preference, allow_legacy=True)
        if normalized in {
            NotificationPreference.EMAIL,
            NotificationPreference.IN_APP,
            NotificationPreference.BOTH,
        }:
            return normalized
        logger.warning(
            "Unknown Job Alert notification preference; defaulting to email.",
            extra={"preference": preference},
        )
        return NotificationPreference.EMAIL

    @staticmethod
    def _normalize_frequency(frequency: str | None) -> str:
        normalized = NotificationFrequency.normalize(
            frequency,
            default=NotificationFrequency.INSTANT,
        )
        if normalized in {
            NotificationFrequency.INSTANT,
            NotificationFrequency.DAILY,
            NotificationFrequency.WEEKLY,
        }:
            return normalized
        logger.warning(
            "Unknown Job Alert frequency; defaulting to instant.",
            extra={"frequency": frequency},
        )
        return NotificationFrequency.INSTANT

    @classmethod
    def _delivery_channels(cls, preference: str) -> tuple[bool, bool]:
        preference = cls._normalize_preference(preference)
        if preference == NotificationPreference.BOTH:
            return True, True
        if preference == NotificationPreference.IN_APP:
            return False, True
        return True, False

    @classmethod
    def _instant_delivery_guard_keys(cls, alert: Any) -> set[tuple[str, str, str]]:
        preference = cls._normalize_preference(alert.notification_preference)
        send_email, create_in_app = cls._delivery_channels(preference)
        channels = []
        if send_email:
            channels.append(NotificationChannel.EMAIL)
        if create_in_app:
            channels.append(NotificationChannel.IN_APP)

        candidate_id = str(getattr(alert, "candidate_id", "") or "")
        alert_id = str(getattr(alert, "alert_id", "") or "")
        return {
            (candidate_id, alert_id, channel)
            for channel in channels
        }

    @staticmethod
    def _daily_window(run_at: datetime) -> tuple[datetime, datetime]:
        anchor = run_at.replace(second=0, microsecond=0)
        return anchor - timedelta(days=1), anchor - timedelta(microseconds=1)

    @staticmethod
    def _weekly_window(run_at: datetime) -> tuple[datetime, datetime]:
        anchor = run_at.replace(second=0, microsecond=0)
        current_monday = anchor - timedelta(days=anchor.weekday())
        return (
            current_monday - timedelta(days=7),
            current_monday - timedelta(microseconds=1),
        )

    @classmethod
    def _due_digest_window_utc(
        cls,
        *,
        frequency: str,
        local_run_at: datetime,
        local_previous_run_at: datetime | None,
    ) -> tuple[datetime, datetime] | None:
        scheduled_at = cls._scheduled_local_datetime(
            frequency=frequency,
            local_run_at=local_run_at,
        )
        if scheduled_at > local_run_at:
            return None
        if local_previous_run_at is not None and scheduled_at <= local_previous_run_at:
            return None

        if frequency == NotificationFrequency.DAILY:
            previous_scheduled_at = scheduled_at - timedelta(days=1)
        else:
            previous_scheduled_at = scheduled_at - timedelta(days=7)

        window_start = cls._as_utc(previous_scheduled_at)
        window_end = cls._as_utc(scheduled_at) - timedelta(microseconds=1)
        return window_start, window_end

    @classmethod
    def _scheduled_local_datetime(
        cls,
        *,
        frequency: str,
        local_run_at: datetime,
    ) -> datetime:
        if frequency == NotificationFrequency.DAILY:
            scheduled_date = local_run_at.date()
            hour = JOB_ALERT_DAILY_HOUR
            minute = JOB_ALERT_DAILY_MINUTE
        else:
            weekly_day = JOB_ALERT_WEEKLY_DAY.strip().lower()
            weekday = _WEEKDAYS.get(weekly_day)
            if weekday is None:
                raise ValueError(f"Invalid JOB_ALERT_WEEKLY_DAY: {JOB_ALERT_WEEKLY_DAY}")
            days_since_schedule = (local_run_at.weekday() - weekday) % 7
            scheduled_date = (local_run_at - timedelta(days=days_since_schedule)).date()
            hour = JOB_ALERT_WEEKLY_HOUR
            minute = JOB_ALERT_WEEKLY_MINUTE

        return datetime.combine(
            scheduled_date,
            datetime.min.time(),
            tzinfo=local_run_at.tzinfo,
        ).replace(hour=hour, minute=minute)

    @classmethod
    def _resolve_timezone_name(cls, alert: Any) -> str:
        timezone_name = getattr(alert, "timezone", None) or JOB_ALERT_DEFAULT_TIMEZONE
        return cls._validate_timezone_name(timezone_name)

    @staticmethod
    def _validate_timezone_name(timezone_name: str) -> str:
        timezone_name = (timezone_name or "").strip()
        if not timezone_name:
            raise ValueError("Timezone must be configured.")
        if timezone_name.upper() != "UTC" and "/" not in timezone_name:
            raise ValueError(f"Invalid IANA timezone: {timezone_name}")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if tz.gettz(timezone_name) is None:
                raise ValueError(f"Invalid IANA timezone: {timezone_name}")
        return timezone_name

    @classmethod
    def _load_timezone(cls, timezone_name: str):
        timezone_name = cls._validate_timezone_name(timezone_name)
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            loaded = tz.gettz(timezone_name)
            if loaded is None:
                raise
            return loaded

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _digest_reference_id(
        *,
        frequency: str,
        window_start: datetime,
        window_end: datetime,
        recipient_id: str,
        alert_id: str | None = None,
    ) -> str:
        return (
            f"JOB_ALERT_{frequency}:"
            f"{recipient_id}:"
            f"{alert_id or 'ALL'}:"
            f"{window_start.isoformat()}:{window_end.isoformat()}"
        )

    @staticmethod
    def _equals(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False

        return left.strip().lower() == right.strip().lower()

    @staticmethod
    def _candidate_name(
        first_name: str | None,
        last_name: str | None,
    ) -> str:
        return " ".join(filter(None, [first_name, last_name])).strip()
