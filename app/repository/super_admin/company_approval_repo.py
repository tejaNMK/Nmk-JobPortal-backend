from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.authentication.users import Users
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.utils.date_range import NormalizedDateRange, normalize_datetime_for_db


class CompanyApprovalRepository:
    @staticmethod
    def _base_query():
        return (
            select(CompanyProfile, EmployerProfile, Users)
            .join(EmployerProfile, EmployerProfile.id == CompanyProfile.employer_id)
            .join(Users, Users.user_id == EmployerProfile.user_id)
            .where(
                EmployerProfile.is_deleted == 0,
                Users.deleted_flag.is_(False),
            )
        )

    @staticmethod
    def _apply_filters(
        query,
        search: Optional[str] = None,
        company: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
    ):
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    CompanyProfile.company_name.ilike(search_term),
                    EmployerProfile.company_name.ilike(search_term),
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.email.ilike(search_term),
                )
            )

        if company:
            query = query.where(CompanyProfile.company_name.ilike(f"%{company}%"))

        if status:
            query = query.where(CompanyProfile.verification_status == status.upper())

        if start_date:
            query = query.where(CompanyProfile.created_at >= normalize_datetime_for_db(start_date))

        if end_date:
            query = query.where(CompanyProfile.created_at <= normalize_datetime_for_db(end_date))
        elif date_range and not start_date:
            start_at = normalize_datetime_for_db(date_range.utc_start)
            end_at = normalize_datetime_for_db(date_range.utc_end_exclusive)
            query = query.where(
                CompanyProfile.created_at >= start_at,
                CompanyProfile.created_at < end_at,
            )

        return query

    @staticmethod
    async def list_company_approvals(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        company: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        query = CompanyApprovalRepository._apply_filters(
            CompanyApprovalRepository._base_query(),
            search=search,
            company=company,
            status=status,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
        )

        total = await session.scalar(select(func.count()).select_from(query.subquery()))

        sort_columns = {
            "company_name": CompanyProfile.company_name,
            "status": CompanyProfile.verification_status,
            "created_at": CompanyProfile.created_at,
            "submitted_at": CompanyProfile.created_at,
            "approved_at": CompanyProfile.approved_at,
            "rejected_at": CompanyProfile.rejected_at,
        }
        sort_column = sort_columns.get(sort_by, CompanyProfile.created_at)
        order_clause = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()

        result = await session.execute(
            query.order_by(order_clause)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0

    @staticmethod
    async def list_pending(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        company: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        return await CompanyApprovalRepository.list_company_approvals(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            company=company,
            status="PENDING",
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @staticmethod
    async def list_history(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        company: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        query = CompanyApprovalRepository._apply_filters(
            CompanyApprovalRepository._base_query().where(
                CompanyProfile.verification_status.in_(("APPROVED", "REJECTED"))
            ),
            search=search,
            company=company,
            status=status,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))

        action_date = func.coalesce(
            CompanyProfile.approved_at,
            CompanyProfile.rejected_at,
            CompanyProfile.verified_at,
            CompanyProfile.updated_at,
        )
        sort_columns = {
            "company_name": CompanyProfile.company_name,
            "status": CompanyProfile.verification_status,
            "created_at": CompanyProfile.created_at,
            "action_date": action_date,
            "approved_at": CompanyProfile.approved_at,
            "rejected_at": CompanyProfile.rejected_at,
        }
        sort_column = sort_columns.get(sort_by, action_date)
        order_clause = sort_column.asc() if sort_order.lower() == "asc" else sort_column.desc()

        result = await session.execute(
            query.order_by(order_clause)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return result.all(), total or 0

    @staticmethod
    async def get_by_company_id(session: AsyncSession, company_id: str):
        result = await session.execute(
            CompanyApprovalRepository._base_query().where(
                CompanyProfile.company_id == company_id
            )
        )
        return result.first()

    @staticmethod
    async def update_verification(
        session: AsyncSession,
        company: CompanyProfile,
        employer: EmployerProfile,
        status: str,
        reason: Optional[str] = None,
    ):
        now = utc_now_naive()
        company.verification_status = status
        company.verified_at = now if status == "APPROVED" else None
        company.approved_at = now if status == "APPROVED" else None
        company.rejected_at = now if status == "REJECTED" else None
        company.rejection_reason = reason if status == "REJECTED" else None
        company.updated_at = now

        employer.verification_status = status
        employer.is_verified = 1 if status == "APPROVED" else 0
        employer.approved_at = now if status == "APPROVED" else None
        employer.rejected_at = now if status == "REJECTED" else None
        employer.rejection_reason = reason if status == "REJECTED" else None
        employer.updated_at = now.isoformat()

        await commit_rollback(session)
        return company, employer
