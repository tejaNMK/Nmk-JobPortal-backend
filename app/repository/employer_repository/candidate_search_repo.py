from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from app.utils.utc import utc_now_naive

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail


class EmployerCandidateSearchRepository:
    @staticmethod
    def _latest_resume_subquery():
        return (
            select(
                CandidateResumeDetail.candidate_id.label("candidate_id"),
                func.max(CandidateResumeDetail.generated_at).label("generated_at"),
            )
            .where(CandidateResumeDetail.is_deleted.is_(False))
            .group_by(CandidateResumeDetail.candidate_id)
            .subquery()
        )

    @staticmethod
    async def search_candidates(
        session: AsyncSession,
        *,
        filters,
    ) -> Tuple[int, List[Tuple[CandidateProfile, Users, Optional[CandidateResumeDetail]]]]:
        latest_resume = EmployerCandidateSearchRepository._latest_resume_subquery()
        base = (
            select(CandidateProfile, Users, CandidateResumeDetail)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .outerjoin(
                latest_resume,
                latest_resume.c.candidate_id == CandidateProfile.candidate_id,
            )
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.generated_at == latest_resume.c.generated_at,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                # Recruiter search visibility is controlled solely by the
                # "Recruiter search" toggle (searchable_flag). It must not
                # depend on the independent "Public link" toggle
                # (profile_visibility).
                CandidateProfile.searchable_flag.is_(True),
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )

        if filters.keyword:
            term = f"%{filters.keyword}%"
            base = base.where(
                or_(
                    Users.first_name.ilike(term),
                    Users.last_name.ilike(term),
                    CandidateProfile.headline.ilike(term),
                    CandidateProfile.summary.ilike(term),
                    CandidateProfile.current_company.ilike(term),
                    CandidateProfile.target_roles.ilike(term),
                )
            )

        if filters.skills:
            skill_conditions = [
                CandidateProfile.skills_summary.ilike(f"%{skill}%")
                for skill in filters.skills
                if skill
            ]
            skill_conditions.extend(
                cast(CandidateResumeDetail.skills_json, String).ilike(f"%{skill}%")
                for skill in filters.skills
                if skill
            )
            if skill_conditions:
                base = base.where(or_(*skill_conditions))

        if filters.experience_min is not None:
            base = base.where(CandidateProfile.total_experience >= filters.experience_min)
        if filters.experience_max is not None:
            base = base.where(CandidateProfile.total_experience <= filters.experience_max)

        if filters.location:
            term = f"%{filters.location}%"
            base = base.where(
                or_(
                    CandidateProfile.current_location.ilike(term),
                    CandidateProfile.preferred_location.ilike(term),
                )
            )

        if filters.preferred_role:
            base = base.where(CandidateProfile.target_roles.ilike(f"%{filters.preferred_role}%"))

        if filters.availability:
            base = base.where(CandidateProfile.notice_period.ilike(f"%{filters.availability}%"))

        if filters.employment_type:
            base = base.where(CandidateProfile.desired_employment.ilike(f"%{filters.employment_type}%"))

        if filters.expected_salary:
            base = base.where(CandidateProfile.salary_expectation.ilike(f"%{filters.expected_salary}%"))

        if filters.work_preference:
            base = base.where(CandidateProfile.work_preference.ilike(f"%{filters.work_preference}%"))

        if filters.profile_completion_min is not None:
            base = base.where(CandidateProfile.profile_completion_pct >= filters.profile_completion_min)

        if filters.updated_within_days is not None:
            since = utc_now_naive() - timedelta(days=filters.updated_within_days)
            base = base.where(CandidateProfile.updated_at >= since)

        # Education, certifications, and work authorization may live in resume JSON or
        # downstream profile extensions. Keep direct filters conservative here so the
        # query stays portable across test databases and Postgres.

        if filters.sort_by == "experience":
            order_by = CandidateProfile.total_experience.desc().nullslast()
        elif filters.sort_by == "profile_completion":
            order_by = CandidateProfile.profile_completion_pct.desc()
        elif filters.sort_by in {"newest", "last_updated"}:
            order_by = CandidateProfile.updated_at.desc()
        else:
            order_by = CandidateProfile.updated_at.desc()

        total = await session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await session.execute(
            base.order_by(order_by)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return int(total or 0), list(rows.all())
