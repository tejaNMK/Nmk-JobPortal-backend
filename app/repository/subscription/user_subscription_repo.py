from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, delete, func, nullslast, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.authentication.role import Role
from app.model.authentication.user_role import UsersRole
from app.model.authentication.users import Users
from app.model.subscription.subscription import Subscription
from app.model.subscription.subscription_history import SubscriptionHistory
from app.model.subscription.subscription_usage import SubscriptionUsage
from app.model.subscription.user_subscription import UserSubscription


LIFETIME_PERIOD_START = datetime(1970, 1, 1)
LIFETIME_PERIOD_END = datetime(9999, 12, 31, 23, 59, 59)


class UserSubscriptionRepository:

    # =========================
    # CREATE
    # =========================
    @staticmethod
    async def create(
        session: AsyncSession,
        user_subscription: UserSubscription,
        *,
        commit: bool = True,
    ):

        session.add(user_subscription)

        if commit:
            await commit_rollback(session)
            await session.refresh(user_subscription)
        else:
            await session.flush()


        return user_subscription

    # =========================
    # GET BY ID
    # =========================
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        user_subscription_id: UUID,
    ):

        result = await session.execute(
            select(UserSubscription).where(
                UserSubscription.user_subscription_id
                == user_subscription_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id_with_details(
        session: AsyncSession,
        user_subscription_id: UUID,
    ):
        result = await session.execute(
            select(UserSubscription, Users, Subscription)
            .outerjoin(Users, Users.user_id == UserSubscription.user_id)
            .outerjoin(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .where(
                UserSubscription.user_subscription_id == user_subscription_id
            )
        )

        return result.one_or_none()

    # =========================
    # GET ACTIVE SUBSCRIPTION
    # =========================
    @staticmethod
    async def get_active_subscription(
        session: AsyncSession,
        user_id: UUID,
        role: str | None = None,
        exclude_user_subscription_id: UUID | None = None,
    ):
        query = select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "ACTIVE",
        )
        if role:
            query = query.where(func.upper(UserSubscription.role) == role.upper())
        if exclude_user_subscription_id:
            query = query.where(
                UserSubscription.user_subscription_id != exclude_user_subscription_id
            )

        result = await session.execute(
            query.order_by(desc(UserSubscription.created_at)).limit(1)
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def list_current_subscription_candidates(
        session: AsyncSession,
        user_id: UUID,
        *,
        expected_type: str | None = None,
        limit: int = 2,
    ):
        now = func.now()
        query = (
            select(UserSubscription, Subscription)
            .join(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "ACTIVE",
                or_(
                    UserSubscription.start_date.is_(None),
                    UserSubscription.start_date <= now,
                ),
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > now,
                ),
                Subscription.is_active.is_(True),
            )
        )
        if expected_type:
            query = query.where(
                func.upper(Subscription.subscription_type) == expected_type.upper(),
                func.upper(UserSubscription.role) == expected_type.upper(),
            )

        result = await session.execute(
            query.order_by(
                nullslast(desc(UserSubscription.start_date)),
                desc(UserSubscription.updated_at),
                desc(UserSubscription.created_at),
            ).limit(limit)
        )
        return result.all()

    @staticmethod
    async def list_users_missing_active_subscription(
        session: AsyncSession,
        role_codes: set[str],
        subscription_role: str | None = None,
    ):
        active_join_conditions = (
            (UserSubscription.user_id == Users.user_id)
            & (UserSubscription.status == "ACTIVE")
        )
        if subscription_role:
            active_join_conditions = active_join_conditions & (
                func.upper(UserSubscription.role) == subscription_role.upper()
            )

        result = await session.execute(
            select(Users, Role.role_code)
            .join(UsersRole, UsersRole.user_id == Users.user_id)
            .join(Role, Role.role_id == UsersRole.role_id)
            .outerjoin(
                UserSubscription,
                active_join_conditions,
            )
            .where(
                Role.role_code.in_(role_codes),
                UserSubscription.user_subscription_id.is_(None),
                Users.deleted_flag.is_(False),
            )
        )

        return result.all()

    @staticmethod
    async def list_by_active_state(
        session: AsyncSession,
        *,
        active: bool,
        role: str | None = None,
    ):
        query = (
            select(UserSubscription, Subscription, Users)
            .join(
                Subscription,
                Subscription.subscription_id
                == UserSubscription.subscription_id,
            )
            .outerjoin(Users, Users.user_id == UserSubscription.user_id)
        )
        if active:
            query = query.where(UserSubscription.status == "ACTIVE")
        else:
            query = query.where(UserSubscription.status != "ACTIVE")
        if role:
            query = query.where(func.upper(UserSubscription.role) == role.upper())

        result = await session.execute(
            query.order_by(desc(UserSubscription.created_at))
        )
        return result.all()

    @staticmethod
    async def get_latest_subscription(
        session: AsyncSession,
        user_id: UUID,
        role: str | None = None,
    ):
        query = select(UserSubscription).where(UserSubscription.user_id == user_id)
        if role:
            query = query.where(func.upper(UserSubscription.role) == role.upper())
        result = await session.execute(
            query.order_by(desc(UserSubscription.created_at)).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_razorpay_order_id(
        session: AsyncSession,
        razorpay_order_id: str,
    ):
        result = await session.execute(
            select(UserSubscription).where(
                UserSubscription.razorpay_order_id == razorpay_order_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_razorpay_order_id_for_update(
        session: AsyncSession,
        razorpay_order_id: str,
    ):
        result = await session.execute(
            select(UserSubscription)
            .where(UserSubscription.razorpay_order_id == razorpay_order_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pending_razorpay_subscription(
        session: AsyncSession,
        *,
        user_id: UUID,
        role: str,
    ):
        result = await session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                func.upper(UserSubscription.role) == role.upper(),
                UserSubscription.payment_gateway == "RAZORPAY",
                UserSubscription.status == "PENDING",
                UserSubscription.payment_status == "PENDING",
                UserSubscription.razorpay_order_id.isnot(None),
            )
            .order_by(desc(UserSubscription.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_pending_razorpay_subscriptions(
        session: AsyncSession,
        *,
        created_before: datetime,
        created_after: datetime,
        limit: int = 50,
    ):
        result = await session.execute(
            select(UserSubscription)
            .where(
                UserSubscription.payment_gateway == "RAZORPAY",
                UserSubscription.status == "PENDING",
                UserSubscription.payment_status == "PENDING",
                UserSubscription.razorpay_order_id.isnot(None),
                UserSubscription.created_at <= created_before,
                UserSubscription.created_at >= created_after,
            )
            .order_by(UserSubscription.created_at.asc())
            .limit(limit)
        )
        return result.scalars().all()

    # =========================
    # GET SUBSCRIPTION HISTORY
    # =========================
    @staticmethod
    async def user_exists(
        session: AsyncSession,
        user_id: UUID,
    ) -> bool:
        result = await session.execute(
            select(Users.user_id).where(
                Users.user_id == user_id,
                Users.deleted_flag.is_(False),
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_active_user_identity(
        session: AsyncSession,
        user_id: UUID,
    ):
        result = await session.execute(
            select(Users.user_id, Users.email).where(
                Users.user_id == user_id,
                Users.deleted_flag.is_(False),
            )
        )
        return result.one_or_none()

    @staticmethod
    async def get_history(
        session: AsyncSession,
        user_id: UUID,
    ):

        result = await session.execute(
            select(UserSubscription, Subscription)
            .outerjoin(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .where(
                UserSubscription.user_id == user_id,
            )
            .order_by(
                desc(UserSubscription.created_at),
            )
        )

        return result.all()

    @staticmethod
    async def add_history(
        session: AsyncSession,
        history: SubscriptionHistory,
        *,
        commit: bool = True,
    ):
        session.add(history)
        if commit:
            await commit_rollback(session)
            await session.refresh(history)
        return history

    @staticmethod
    async def get_usage(
        session: AsyncSession,
        user_subscription_id: UUID,
        feature_name: str,
        period_start=None,
        period_end=None,
    ):
        period_start, period_end = UserSubscriptionRepository._usage_period(
            period_start,
            period_end,
        )
        result = await session.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.user_subscription_id == user_subscription_id,
                SubscriptionUsage.feature_name == feature_name,
                SubscriptionUsage.period_start == period_start,
                SubscriptionUsage.period_end == period_end,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _usage_period(period_start=None, period_end=None):
        if period_start is None and period_end is None:
            return (LIFETIME_PERIOD_START, LIFETIME_PERIOD_END)
        if period_start is None or period_end is None:
            raise ValueError("Both period_start and period_end are required.")
        return period_start, period_end

    @staticmethod
    async def increment_usage(
        session: AsyncSession,
        *,
        user_subscription_id: UUID,
        user_id: UUID,
        feature_name: str,
        amount: int = 1,
        period_start=None,
        period_end=None,
        commit: bool = True,
    ):
        if amount <= 0:
            raise ValueError("Usage increment amount must be positive.")
        period_start, period_end = UserSubscriptionRepository._usage_period(
            period_start,
            period_end,
        )

        statement = insert(SubscriptionUsage).values(
            user_subscription_id=user_subscription_id,
            user_id=user_id,
            feature_name=feature_name,
            period_start=period_start,
            period_end=period_end,
            used_count=amount,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_subscription_usage_feature",
            set_={
                "used_count": SubscriptionUsage.used_count + amount,
                "updated_at": func.now(),
            },
        ).returning(SubscriptionUsage.usage_id)
        result = await session.execute(statement)
        usage_id = result.scalar_one()
        if commit:
            await commit_rollback(session)
        else:
            await session.flush()
        usage = await session.get(SubscriptionUsage, usage_id)
        return usage

    @staticmethod
    async def expire_duplicate_active_subscriptions(
        session: AsyncSession,
        *,
        user_id: UUID,
        role: str,
        keep_user_subscription_id: UUID,
    ) -> int:
        result = await session.execute(
            update(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                func.upper(UserSubscription.role) == role.upper(),
                UserSubscription.status == "ACTIVE",
                UserSubscription.user_subscription_id != keep_user_subscription_id,
            )
            .values(status="EXPIRED", updated_at=func.now())
            .execution_options(synchronize_session="fetch")
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def reset_usage(
        session: AsyncSession,
        user_subscription_id: UUID,
        feature_name: str | None = None,
    ):
        query = delete(SubscriptionUsage).where(
            SubscriptionUsage.user_subscription_id == user_subscription_id
        )
        if feature_name:
            query = query.where(SubscriptionUsage.feature_name == feature_name)
        await session.execute(query)

    @staticmethod
    async def list_usage(
        session: AsyncSession,
        user_subscription_id: UUID,
    ):
        result = await session.execute(
            select(SubscriptionUsage)
            .where(SubscriptionUsage.user_subscription_id == user_subscription_id)
            .order_by(SubscriptionUsage.feature_name.asc())
        )
        return result.scalars().all()

    # =========================
    # UPDATE
    # =========================
    @staticmethod
    async def update(
        session: AsyncSession,
        subscription: UserSubscription,
        *,
        commit: bool = True,
    ):

        session.add(subscription)

        if commit:
            await commit_rollback(session)
            await session.refresh(subscription)
        else:
            await session.flush()

        return subscription

    # =========================
    # EXPIRE ACTIVE SUBSCRIPTION
    # =========================
    @staticmethod
    async def expire_active_subscription(
        session: AsyncSession,
        user_id: UUID,
    ):

        active_subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
        )

        if not active_subscription:
            return None

        active_subscription.status = "EXPIRED"

        session.add(active_subscription)

        await commit_rollback(session)

        return active_subscription

    # =========================
    # CANCEL SUBSCRIPTION
    # =========================
    @staticmethod
    async def cancel_subscription(
        session: AsyncSession,
        user_subscription: UserSubscription,
        *,
        commit: bool = True,
    ):

        user_subscription.status = "CANCELLED"

        session.add(user_subscription)

        if commit:
            await commit_rollback(session)
            await session.refresh(user_subscription)
        else:
            await session.flush()

        return user_subscription

    # =========================
    # DELETE
    # =========================
    @staticmethod
    async def delete(
        session: AsyncSession,
        subscription: UserSubscription,
    ):

        await session.delete(subscription)

        await commit_rollback(session)
