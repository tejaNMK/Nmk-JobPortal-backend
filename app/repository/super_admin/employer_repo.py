from datetime import datetime, timezone
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import commit_rollback
from app.model.authentication.role import Role
from app.model.authentication.user_role import UsersRole
from app.model.authentication.users import Users
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job
from app.model.subscription.subscription import Subscription
from app.model.subscription.user_subscription import UserSubscription


class EmployerRepository:

    @staticmethod
    async def list_employers(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        query = (
            select(Users, EmployerProfile, Subscription.subscription_name)
            .join(
                EmployerProfile,
                EmployerProfile.user_id == Users.user_id,
            )
            .outerjoin(
                UserSubscription,
                (UserSubscription.user_id == Users.user_id)
                & (UserSubscription.status == "ACTIVE"),
            )
            .outerjoin(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .options(selectinload(Users.roles))
            .where(
                Users.deleted_flag.is_(False),
                EmployerProfile.is_deleted == 0,
            )
        )

        if search:
            search_term = f"%{search}%"

            query = query.where(
                or_(
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.email.ilike(search_term),
                    EmployerProfile.company_name.ilike(search_term),
                )
            )

        count_query = (
            select(func.count())
            .select_from(query.subquery())
        )

        total = await session.scalar(count_query)

        sort_key = (sort_by or "created_at").lower()
        sort_direction = (sort_order or "desc").lower()
        if sort_key == "oldest":
            sort_key = "created_at"
            sort_direction = "asc"
        elif sort_key == "newest":
            sort_key = "created_at"
            sort_direction = "desc"

        sort_columns = {
            "created_at": Users.created_at,
            "registered_date": Users.created_at,
            "name": Users.first_name,
            "company_name": EmployerProfile.company_name,
        }
        sort_column = sort_columns.get(sort_key, Users.created_at)
        order_by = sort_column.asc() if sort_direction == "asc" else sort_column.desc()

        result = await session.execute(
            query.order_by(order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0

    @staticmethod
    async def get_user(
        session: AsyncSession,
        user_id,
    ):

        result = await session.execute(
            select(Users)
            .options(selectinload(Users.roles))
            .where(
                Users.user_id == user_id
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def get_employer(
        session: AsyncSession,
        employer_id: str,
    ):
        result = await session.execute(
            select(Users, EmployerProfile)
            .join(EmployerProfile, EmployerProfile.user_id == Users.user_id)
            .options(selectinload(Users.roles))
            .where(
                EmployerProfile.id == employer_id,
                EmployerProfile.is_deleted == 0,
                Users.deleted_flag.is_(False),
            )
        )
        return result.first()

    @staticmethod
    async def get_job_counts(
        session: AsyncSession,
        employer_id: str,
    ):
        result = await session.execute(
            select(
                func.count(Job.job_id).label("total_jobs"),
                func.count()
                .filter(Job.status == "PUBLISHED", Job.is_deleted.is_(False))
                .label("active_jobs"),
                func.count()
                .filter(
                    or_(Job.closed_at.is_not(None), Job.status == "CLOSED"),
                    Job.is_deleted.is_(False),
                )
                .label("closed_jobs"),
            )
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
            )
        )
        row = result.one()
        return {
            "total_jobs": row.total_jobs or 0,
            "active_jobs": row.active_jobs or 0,
            "closed_jobs": row.closed_jobs or 0,
        }

    @staticmethod
    async def get_active_subscription(
        session: AsyncSession,
        user_id,
    ):
        result = await session.execute(
            select(UserSubscription, Subscription)
            .join(Subscription, Subscription.subscription_id == UserSubscription.subscription_id)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "ACTIVE",
            )
            .order_by(UserSubscription.created_at.desc())
            .limit(1)
        )
        return result.first()

    @staticmethod
    async def update_employer(
        session: AsyncSession,
        employer_id: str,
        user_updates: dict,
        employer_updates: dict,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            return None

        user, employer = row
        for key, value in user_updates.items():
            setattr(user, key, value)
        for key, value in employer_updates.items():
            setattr(employer, key, value)
        employer.updated_at = datetime.now(timezone.utc)

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def update_status(
        session: AsyncSession,
        employer_id: str,
        status: str,
        reason: Optional[str] = None,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            return None

        user, employer = row
        employer.status = status
        employer.suspension_reason = reason if status == "SUSPENDED" else None
        user.user_status = "SUSPENDED" if status == "SUSPENDED" else status

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def update_verification(
        session: AsyncSession,
        employer_id: str,
        verification_status: str,
        reason: Optional[str] = None,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            return None

        user, employer = row
        now = utc_now_naive()
        employer.verification_status = verification_status
        employer.is_verified = 1 if verification_status == "APPROVED" else 0
        employer.approved_at = now if verification_status == "APPROVED" else None
        employer.rejected_at = now if verification_status == "REJECTED" else None
        employer.rejection_reason = reason if verification_status == "REJECTED" else None
        employer.updated_at = now.isoformat()

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def approve_employer_company(
        session: AsyncSession,
        employer_id: str,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            return None

        user, employer = row
        now = utc_now_naive()
        employer.verification_status = "APPROVED"
        employer.is_verified = 1
        employer.approved_at = now
        employer.rejected_at = None
        employer.rejection_reason = None
        employer.updated_at = now.isoformat()

        company_result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.employer_id == employer.id)
        )
        company = company_result.scalar_one_or_none()
        if company:
            company.verification_status = "APPROVED"
            company.verified_at = now
            company.approved_at = now
            company.rejected_at = None
            company.rejection_reason = None
            company.updated_at = now

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def soft_delete_employer(
        session: AsyncSession,
        employer_id: str,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            return None

        user, employer = row
        now = utc_now_naive()
        employer.is_deleted = 1
        employer.deleted_at = now.isoformat()
        user.deleted_flag = True
        user.deleted_at = now

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def soft_delete_employer_by_user_id(
        session: AsyncSession,
        user_id,
    ):
        result = await session.execute(
            select(Users, EmployerProfile)
            .join(EmployerProfile, EmployerProfile.user_id == Users.user_id)
            .where(
                Users.user_id == user_id,
                Users.deleted_flag.is_(False),
                EmployerProfile.is_deleted == 0,
            )
        )
        row = result.first()
        if not row:
            return None

        user, employer = row
        now = utc_now_naive()
        employer.is_deleted = 1
        employer.deleted_at = now.isoformat()
        employer.status = "INACTIVE"
        employer.updated_at = now.isoformat()
        user.deleted_flag = True
        user.deleted_at = now
        user.user_status = "INACTIVE"

        await commit_rollback(session)
        return user, employer

    @staticmethod
    async def get_role(
        session: AsyncSession,
        role_code: str,
    ):

        result = await session.execute(
            select(Role)
            .where(
                Role.role_code == role_code
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def assign_role(
        session: AsyncSession,
        user_id,
        role_id,
    ):

        existing = await session.execute(
            select(UsersRole).where(
                UsersRole.user_id == user_id,
                UsersRole.role_id == role_id,
            )
        )

        if existing.scalar_one_or_none():
            return None

        assignment = UsersRole(
            user_id=user_id,
            role_id=role_id,
        )

        session.add(assignment)

        await commit_rollback(session)

        return assignment

    @staticmethod
    async def get_user_role(
        session: AsyncSession,
        user_id,
        role_id,
    ):

        result = await session.execute(
            select(UsersRole).where(
                UsersRole.user_id == user_id,
                UsersRole.role_id == role_id,
            )
        )

        return result.scalar_one_or_none()

    @staticmethod
    async def remove_role(
        session: AsyncSession,
        user_role: UsersRole,
    ):

        await session.delete(user_role)

        await commit_rollback(session)
