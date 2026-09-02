# ============================================================
# Imports
# ============================================================

from sqlalchemy import asc, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.job import Job

# ============================================================
# Candidate List Repository
# ============================================================

class CandidateListRepo:

    @classmethod
    async def get_candidates(
        cls,
        session: AsyncSession,
        page: int,
        page_size: int,
        search: str | None = None,
        status: str | None = None,
        skills: str | None = None,
        sort_by: str = "name",
        sort_order: str = "asc",
    ) -> tuple[list, int]:

        query = (
            select(
                CandidateProfile,
                Users,
                JobApplication,
                Job,
            )
            .join(
                Users,
                CandidateProfile.user_id == Users.user_id,
            )
            .outerjoin(
                JobApplication,
                CandidateProfile.candidate_id
                == JobApplication.candidate_id,
            )
            .outerjoin(
                Job,
                JobApplication.job_id == Job.job_id,
            )
            .where(
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )

        # ====================================================
        # Search
        # ====================================================

        if search:
            search = search.strip()

            query = query.where(
                or_(
                    Users.first_name.ilike(
                        f"%{search}%"
                    ),
                    Users.last_name.ilike(
                        f"%{search}%"
                    ),
                    Users.email.ilike(
                        f"%{search}%"
                    ),
                    CandidateProfile.skills_summary.ilike(
                        f"%{search}%"
                   ),
                )
            )

        # ====================================================
        # Status Filter
        # ====================================================

        if status:
            query = query.where(
                CandidateProfile.status == status
            )

        # ====================================================
        # Skills Filter
        # ====================================================

        if skills:
            query = query.where(
                CandidateProfile.skills_summary.ilike(
                    f"%{skills}%"
                )
            )

        # ====================================================
        # Sorting
        # ====================================================

        if sort_by == "date":
            order_column = CandidateProfile.created_at

        elif sort_by == "status":
            order_column = CandidateProfile.status

        else:
            order_column = Users.first_name

        query = query.order_by(
            asc(order_column)
            if sort_order == "asc"
            else desc(order_column)
        )

        # ====================================================
        # Count
        # ====================================================

        count_query = (
            select(func.count())
            .select_from(query.subquery())
        )

        total_records = (
            await session.execute(count_query)
        ).scalar()

        # ====================================================
        # Pagination
        # ====================================================

        query = query.offset(
            (page - 1) * page_size
        ).limit(page_size)

        result = await session.execute(query)

        return (
            result.all(),
            total_records,
        )