from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.subscription.subscription import Subscription
from app.model.subscription.user_subscription import UserSubscription


class SubscriptionRepository:

    @staticmethod
    async def create(
        session: AsyncSession,
        subscription: Subscription,
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

    @staticmethod
    async def get_all(
        session: AsyncSession,
        *,
        subscription_type: str | None = None,
        status: str | None = None,
        billing_cycle: str | None = None,
        search: str | None = None,
    ):

        query = select(Subscription)
        if subscription_type:
            normalized_type = subscription_type.upper()
            if normalized_type in {"EMPLOYER_ADMIN", "EMPLOYER/ADMIN", "ADMIN"}:
                query = query.where(
                    func.upper(Subscription.subscription_type).in_(
                        ["EMPLOYER", "ADMIN"]
                    )
                )
            else:
                query = query.where(
                    func.upper(Subscription.subscription_type) == normalized_type
                )
        if status and status.lower() != "all":
            query = query.where(
                Subscription.is_active.is_(status.lower() == "active")
            )
        if billing_cycle and billing_cycle.lower() != "all":
            query = query.where(
                func.lower(Subscription.billing_cycle) == billing_cycle.lower()
            )
        if search:
            pattern = f"%{search}%"
            query = query.where(
                Subscription.subscription_name.ilike(pattern)
                | Subscription.description.ilike(pattern)
            )

        result = await session.execute(
            query.order_by(
                Subscription.display_order.asc(),
                Subscription.price.asc(),
                Subscription.created_at.asc(),
            )
        )

        return result.scalars().all()

    @staticmethod
    async def get_default(
        session: AsyncSession,
        subscription_type: str,
    ):
        result = await session.execute(
            select(Subscription).where(
                func.upper(Subscription.subscription_type)
                == subscription_type.upper(),
                Subscription.is_default.is_(True),
                Subscription.is_active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def count_user_assignments(
        session: AsyncSession,
        subscription_id: UUID,
    ) -> int:
        result = await session.execute(
            select(func.count(UserSubscription.user_subscription_id)).where(
                UserSubscription.subscription_id == subscription_id
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def clear_default_for_type(
        session: AsyncSession,
        subscription_type: str,
        exclude_subscription_id: UUID | None = None,
    ):
        query = (
            update(Subscription)
            .where(
                func.upper(Subscription.subscription_type)
                == subscription_type.upper(),
                Subscription.is_default.is_(True),
            )
            .values(is_default=False)
            .execution_options(synchronize_session="fetch")
        )
        if exclude_subscription_id:
            query = query.where(
                Subscription.subscription_id != exclude_subscription_id
            )

        await session.execute(query)

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        subscription_id: UUID,
    ):

        result = await session.execute(

            select(Subscription).where(
                Subscription.subscription_id == subscription_id
            )

        )

        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        session: AsyncSession,
        subscription: Subscription,
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

    @staticmethod
    async def delete(
        session: AsyncSession,
        subscription: Subscription,
        *,
        commit: bool = True,
    ):

        await session.delete(subscription)

        if commit:
            await commit_rollback(session)
        else:
            await session.flush()

    @staticmethod
    async def exists_by_name(
        session: AsyncSession,
        name: str,
    ):

        result = await session.execute(

            select(Subscription).where(
                func.lower(Subscription.subscription_name)
                == name.lower()
            )

        )

        return result.scalar_one_or_none()
