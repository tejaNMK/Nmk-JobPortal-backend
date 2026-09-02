import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import (
    PAYMENT_RECONCILIATION_ENABLED,
    PAYMENT_RECONCILIATION_INTERVAL_MINUTES,
    PAYMENT_RECONCILIATION_PENDING_MINUTES,
    PAYMENT_RECONCILIATION_STALE_HOURS,
    engine,
)
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.service.payment_service import RazorpayPaymentService


logger = logging.getLogger(__name__)

PAYMENT_RECONCILIATION_JOB_ID = "razorpay-payment-reconciliation"
PAYMENT_RECONCILIATION_LOCK_ID = 718_420_002_401


async def execute_payment_reconciliation(
    *,
    run_at_utc: datetime | None = None,
    db_engine: AsyncEngine = engine,
) -> bool:
    run_at_utc = run_at_utc or datetime.now(UTC)
    if run_at_utc.tzinfo is not None:
        run_at_utc = run_at_utc.replace(tzinfo=None)
    created_before = run_at_utc - timedelta(
        minutes=PAYMENT_RECONCILIATION_PENDING_MINUTES
    )
    created_after = run_at_utc - timedelta(
        hours=PAYMENT_RECONCILIATION_STALE_HOURS
    )

    try:
        async with db_engine.connect() as connection:
            lock_result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": PAYMENT_RECONCILIATION_LOCK_ID},
            )
            if not bool(lock_result.scalar()):
                logger.info("Skipping payment reconciliation; lock is held.")
                return False

            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                ) as session:
                    pending_rows = (
                        await UserSubscriptionRepository.list_pending_razorpay_subscriptions(
                            session=session,
                            created_before=created_before,
                            created_after=created_after,
                        )
                    )
                    for user_subscription in pending_rows:
                        try:
                            await RazorpayPaymentService.reconcile_pending_order(
                                session,
                                user_subscription,
                            )
                        except Exception:
                            logger.exception(
                                "Payment reconciliation failed for a pending order.",
                                extra={
                                    "user_subscription_id": str(
                                        user_subscription.user_subscription_id
                                    ),
                                    "razorpay_order_id": (
                                        user_subscription.razorpay_order_id
                                    ),
                                },
                            )
                return True
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": PAYMENT_RECONCILIATION_LOCK_ID},
                )
    except Exception:
        logger.exception("Payment reconciliation job failed.")
        return False


class PaymentReconciliationScheduler:
    def __init__(
        self,
        *,
        db_engine: AsyncEngine = engine,
        interval_minutes: int = PAYMENT_RECONCILIATION_INTERVAL_MINUTES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.db_engine = db_engine
        self.interval_seconds = max(int(interval_minutes), 1) * 60
        self.sleep = sleep
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task:
            logger.info("Payment reconciliation scheduler is already running.")
            return
        self._task = asyncio.create_task(
            self._run_loop(),
            name=PAYMENT_RECONCILIATION_JOB_ID,
        )
        logger.info(
            "Payment reconciliation scheduler started.",
            extra={"interval_seconds": self.interval_seconds},
        )

    async def shutdown(self) -> None:
        task = self._task
        self._task = None
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Payment reconciliation scheduler stopped.")

    async def _run_loop(self) -> None:
        while True:
            await self.sleep(self.interval_seconds)
            await execute_payment_reconciliation(db_engine=self.db_engine)


def start_payment_reconciliation_scheduler(app) -> None:
    if not PAYMENT_RECONCILIATION_ENABLED:
        logger.info("Payment reconciliation scheduler is disabled.")
        return
    if getattr(app.state, "payment_reconciliation_scheduler", None):
        logger.info("Payment reconciliation scheduler is already registered.")
        return
    scheduler = PaymentReconciliationScheduler()
    scheduler.start()
    app.state.payment_reconciliation_scheduler = scheduler


async def shutdown_payment_reconciliation_scheduler(app) -> None:
    scheduler = getattr(app.state, "payment_reconciliation_scheduler", None)
    if not scheduler:
        return
    await scheduler.shutdown()
    app.state.payment_reconciliation_scheduler = None
