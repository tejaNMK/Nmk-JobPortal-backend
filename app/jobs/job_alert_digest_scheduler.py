import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from dateutil import tz
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import (
    JOB_ALERT_DEFAULT_TIMEZONE,
    JOB_ALERT_SCHEDULER_ENABLED,
    JOB_ALERT_SCHEDULER_INTERVAL_MINUTES,
    engine,
)
from app.service.job_alert_notification_service import JobAlertNotificationService

logger = logging.getLogger(__name__)

JOB_ALERT_DAILY_JOB_ID = "job-alert-daily-digest"
JOB_ALERT_WEEKLY_JOB_ID = "job-alert-weekly-digest"
JOB_ALERT_DUE_DIGEST_JOB_ID = "job-alert-due-digests"

JOB_ALERT_DAILY_LOCK_ID = 718_420_001_401
JOB_ALERT_WEEKLY_LOCK_ID = 718_420_001_402
JOB_ALERT_DUE_DIGEST_LOCK_ID = 718_420_001_403

DigestRunner = Callable[[AsyncSession, datetime], Awaitable[None]]


def _load_timezone(timezone_name: str):
    timezone_name = (timezone_name or "").strip()
    if timezone_name.upper() != "UTC" and "/" not in timezone_name:
        raise ZoneInfoNotFoundError(f"No time zone found with key {timezone_name}")

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        loaded = tz.gettz(timezone_name)
        if loaded is None:
            raise
        return loaded


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _run_digest_with_lock(
    *,
    db_engine: AsyncEngine,
    lock_id: int,
    job_id: str,
    run_at: datetime,
    runner: DigestRunner,
) -> bool:
    run_at = _as_utc(run_at)
    logger.info(
        "Starting Job Alert digest job.",
        extra={"job_id": job_id, "run_at": run_at.isoformat()},
    )

    try:
        async with db_engine.connect() as connection:
            lock_result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            )
            lock_acquired = bool(lock_result.scalar())

            if not lock_acquired:
                logger.info(
                    "Skipping Job Alert digest job; another instance holds the lock.",
                    extra={"job_id": job_id, "lock_id": lock_id},
                )
                return False

            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                ) as session:
                    await runner(session, run_at)

                logger.info(
                    "Completed Job Alert digest job.",
                    extra={"job_id": job_id, "run_at": run_at.isoformat()},
                )
                return True

            except Exception:
                logger.exception(
                    "Job Alert digest job failed.",
                    extra={"job_id": job_id, "run_at": run_at.isoformat()},
                )
                return False

            finally:
                try:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": lock_id},
                    )
                except Exception:
                    logger.exception(
                        "Failed to release Job Alert digest advisory lock.",
                        extra={"job_id": job_id, "lock_id": lock_id},
                    )

    except Exception:
        logger.exception(
            "Job Alert digest job could not acquire a database connection.",
            extra={"job_id": job_id, "run_at": run_at.isoformat()},
        )
        return False


async def execute_daily_digest(
    *,
    run_at: datetime | None = None,
    db_engine: AsyncEngine = engine,
) -> bool:
    run_at = run_at or datetime.now(_load_timezone(JOB_ALERT_DEFAULT_TIMEZONE))
    return await _run_digest_with_lock(
        db_engine=db_engine,
        lock_id=JOB_ALERT_DAILY_LOCK_ID,
        job_id=JOB_ALERT_DAILY_JOB_ID,
        run_at=run_at,
        runner=lambda session, digest_run_at: (
            JobAlertNotificationService.process_daily_notifications(
                session=session,
                run_at=digest_run_at,
            )
        ),
    )


async def execute_weekly_digest(
    *,
    run_at: datetime | None = None,
    db_engine: AsyncEngine = engine,
) -> bool:
    run_at = run_at or datetime.now(_load_timezone(JOB_ALERT_DEFAULT_TIMEZONE))
    return await _run_digest_with_lock(
        db_engine=db_engine,
        lock_id=JOB_ALERT_WEEKLY_LOCK_ID,
        job_id=JOB_ALERT_WEEKLY_JOB_ID,
        run_at=run_at,
        runner=lambda session, digest_run_at: (
            JobAlertNotificationService.process_weekly_notifications(
                session=session,
                run_at=digest_run_at,
            )
        ),
    )


async def execute_due_digests(
    *,
    run_at_utc: datetime | None = None,
    previous_run_at_utc: datetime | None = None,
    db_engine: AsyncEngine = engine,
) -> bool:
    run_at_utc = _as_utc(run_at_utc or datetime.now(UTC))
    previous_run_at_utc = (
        _as_utc(previous_run_at_utc)
        if previous_run_at_utc is not None
        else None
    )
    return await _run_digest_with_lock(
        db_engine=db_engine,
        lock_id=JOB_ALERT_DUE_DIGEST_LOCK_ID,
        job_id=JOB_ALERT_DUE_DIGEST_JOB_ID,
        run_at=run_at_utc,
        runner=lambda session, digest_run_at: (
            JobAlertNotificationService.process_due_notifications(
                session=session,
                run_at_utc=digest_run_at,
                previous_run_at_utc=previous_run_at_utc,
            )
        ),
    )


class JobAlertDigestScheduler:
    def __init__(
        self,
        *,
        db_engine: AsyncEngine = engine,
        timezone_name: str = JOB_ALERT_DEFAULT_TIMEZONE,
        interval_minutes: int = JOB_ALERT_SCHEDULER_INTERVAL_MINUTES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.db_engine = db_engine
        self.timezone = _load_timezone(timezone_name)
        self.interval_seconds = max(int(interval_minutes), 1) * 60
        self.sleep = sleep
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        if self._tasks:
            logger.info("Job Alert digest scheduler is already running.")
            return

        self._tasks = [
            asyncio.create_task(
                self._run_due_loop(),
                name=JOB_ALERT_DUE_DIGEST_JOB_ID,
            ),
        ]
        logger.info(
            "Job Alert digest scheduler started.",
            extra={
                "interval_seconds": self.interval_seconds,
                "timezone": str(self.timezone),
            },
        )

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        self._tasks = []

        for task in tasks:
            task.cancel()

        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        if tasks:
            logger.info("Job Alert digest scheduler stopped.")

    async def _run_due_loop(self) -> None:
        previous_run_at_utc: datetime | None = None

        while True:
            await self.sleep(self.interval_seconds)
            run_at_utc = datetime.now(UTC)
            try:
                await execute_due_digests(
                    run_at_utc=run_at_utc,
                    previous_run_at_utc=previous_run_at_utc,
                    db_engine=self.db_engine,
                )
                previous_run_at_utc = run_at_utc
            except Exception:
                logger.exception(
                    "Unexpected failure in Job Alert due digest loop.",
                    extra={"job_id": JOB_ALERT_DUE_DIGEST_JOB_ID},
                )


def start_job_alert_digest_scheduler(app) -> None:
    if not JOB_ALERT_SCHEDULER_ENABLED:
        logger.info("Job Alert digest scheduler is disabled.")
        return

    if getattr(app.state, "job_alert_digest_scheduler", None):
        logger.info("Job Alert digest scheduler is already registered.")
        return

    scheduler = JobAlertDigestScheduler()
    scheduler.start()
    app.state.job_alert_digest_scheduler = scheduler


async def shutdown_job_alert_digest_scheduler(app) -> None:
    scheduler = getattr(app.state, "job_alert_digest_scheduler", None)
    if not scheduler:
        return

    await scheduler.shutdown()
    app.state.job_alert_digest_scheduler = None


async def _run_manual_digest(frequency: str) -> int:
    if frequency == "daily":
        return 0 if await execute_daily_digest() else 1
    if frequency == "weekly":
        return 0 if await execute_weekly_digest() else 1
    if frequency == "due":
        return 0 if await execute_due_digests() else 1
    raise ValueError(f"Unsupported frequency: {frequency}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Job Alert digest notifications manually.",
    )
    parser.add_argument("frequency", choices=["daily", "weekly", "due"])
    args = parser.parse_args()

    raise SystemExit(asyncio.run(_run_manual_digest(args.frequency)))


if __name__ == "__main__":
    main()
