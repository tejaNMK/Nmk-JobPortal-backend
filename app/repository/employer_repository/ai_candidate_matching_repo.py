from __future__ import annotations

from typing import Optional

from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.ai_candidate_match import AICandidateMatch
from app.model.employer_model.candidate_invitation import CandidateInvitation
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job


class AICandidateMatchingRepository:
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
    async def get_employer_id(session: AsyncSession, user_id) -> Optional[str]:
        result = await session.execute(
            select(EmployerProfile.id).where(EmployerProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_owned_job(session: AsyncSession, *, employer_id: str, job_id: str) -> Optional[Job]:
        result = await session.execute(
            select(Job)
            .where(
                Job.job_id == job_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
            )
            .options(selectinload(Job.skills))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_candidate_pool(
        session: AsyncSession,
        *,
        employer_id: str,
        job_id: str,
        scope: str,
        limit: int,
    ):
        latest_resume = AICandidateMatchingRepository._latest_resume_subquery()
        application_join = and_(
            JobApplication.candidate_id == CandidateProfile.candidate_id,
            JobApplication.job_id == job_id,
            JobApplication.is_deleted.is_(False),
        )
        query = (
            select(CandidateProfile, Users, CandidateResumeDetail, JobApplication)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .outerjoin(JobApplication, application_join)
            .outerjoin(latest_resume, latest_resume.c.candidate_id == CandidateProfile.candidate_id)
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
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )

        discovery_allowed = and_(
            CandidateProfile.searchable_flag.is_(True),
            CandidateProfile.search_engine_indexing.is_(True),
        )
        if scope == "applicants":
            query = query.where(JobApplication.application_id.is_not(None))
        elif scope == "discovery":
            query = query.where(
                JobApplication.application_id.is_(None),
                discovery_allowed,
            )
        else:
            query = query.where(
                or_(
                    JobApplication.application_id.is_not(None),
                    discovery_allowed,
                )
            )

        rows = await session.execute(
            query.order_by(
                JobApplication.applied_at.desc().nullslast(),
                CandidateProfile.updated_at.desc(),
            ).limit(limit)
        )
        return rows.all()

    @staticmethod
    async def upsert_match(session: AsyncSession, match: AICandidateMatch) -> AICandidateMatch:
        result = await session.execute(
            select(AICandidateMatch).where(
                AICandidateMatch.job_id == match.job_id,
                AICandidateMatch.candidate_id == match.candidate_id,
            )
        )
        existing = result.scalar_one_or_none()
        if not existing:
            session.add(match)
            return match

        for field in (
            "application_id",
            "source_type",
            "overall_score",
            "skills_score",
            "experience_score",
            "title_domain_score",
            "education_score",
            "location_score",
            "preferred_skills_score",
            "semantic_score",
            "matched_skills",
            "missing_required_skills",
            "matched_preferred_skills",
            "strengths",
            "gaps",
            "hard_requirements",
            "preferred_requirements",
            "semantic_signals",
            "ai_summary",
            "recommendation",
            "scoring_version",
            "job_updated_at",
            "candidate_updated_at",
            "resume_generated_at",
        ):
            setattr(existing, field, getattr(match, field))
        session.add(existing)
        return existing

    @staticmethod
    def _filtered_matches_query(*, employer_id: str, job_id: str, filters):
        latest_resume = AICandidateMatchingRepository._latest_resume_subquery()
        query = (
            select(AICandidateMatch, CandidateProfile, Users, Job, CandidateResumeDetail)
            .join(Job, Job.job_id == AICandidateMatch.job_id)
            .join(CandidateProfile, CandidateProfile.candidate_id == AICandidateMatch.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .outerjoin(latest_resume, latest_resume.c.candidate_id == CandidateProfile.candidate_id)
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.generated_at == latest_resume.c.generated_at,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(
                AICandidateMatch.job_id == job_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )
        if filters.min_score is not None:
            query = query.where(AICandidateMatch.overall_score >= filters.min_score)
        if filters.skills:
            conditions = []
            for skill in filters.skills:
                term = f"%{skill}%"
                conditions.extend(
                    [
                        cast(AICandidateMatch.matched_skills, String).ilike(term),
                        cast(AICandidateMatch.missing_required_skills, String).ilike(term),
                        cast(AICandidateMatch.matched_preferred_skills, String).ilike(term),
                    ]
                )
            query = query.where(or_(*conditions))
        if filters.experience_min is not None:
            query = query.where(CandidateProfile.total_experience >= filters.experience_min)
        if filters.experience_max is not None:
            query = query.where(CandidateProfile.total_experience <= filters.experience_max)
        if filters.location:
            term = f"%{filters.location}%"
            query = query.where(
                or_(
                    CandidateProfile.current_location.ilike(term),
                    CandidateProfile.preferred_location.ilike(term),
                )
            )
        if filters.education:
            query = query.where(cast(AICandidateMatch.hard_requirements, String).ilike(f"%{filters.education}%"))
        if filters.availability:
            query = query.where(CandidateProfile.notice_period.ilike(f"%{filters.availability}%"))
        if filters.candidate_status:
            query = query.where(CandidateProfile.status == filters.candidate_status.upper())
        if filters.applied is True:
            query = query.where(AICandidateMatch.application_id.is_not(None))
        elif filters.applied is False:
            query = query.where(AICandidateMatch.application_id.is_(None))
        if filters.invited is True:
            query = query.where(
                exists(
                    select(CandidateInvitation.invitation_id).where(
                        CandidateInvitation.job_id == AICandidateMatch.job_id,
                        CandidateInvitation.candidate_id == AICandidateMatch.candidate_id,
                        CandidateInvitation.employer_id == employer_id,
                    )
                )
            )
        elif filters.invited is False:
            query = query.where(
                ~exists(
                    select(CandidateInvitation.invitation_id).where(
                        CandidateInvitation.job_id == AICandidateMatch.job_id,
                        CandidateInvitation.candidate_id == AICandidateMatch.candidate_id,
                        CandidateInvitation.employer_id == employer_id,
                    )
                )
            )
        return query

    @staticmethod
    async def list_matches(session: AsyncSession, *, employer_id: str, job_id: str, filters):
        query = AICandidateMatchingRepository._filtered_matches_query(
            employer_id=employer_id,
            job_id=job_id,
            filters=filters,
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await session.execute(
            query.order_by(AICandidateMatch.overall_score.desc(), AICandidateMatch.updated_at.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return int(total or 0), rows.all()

    @staticmethod
    async def get_match_detail(
        session: AsyncSession,
        *,
        employer_id: str,
        job_id: str,
        candidate_id: str,
    ):
        latest_resume = AICandidateMatchingRepository._latest_resume_subquery()
        result = await session.execute(
            select(AICandidateMatch, CandidateProfile, Users, Job, CandidateResumeDetail)
            .join(Job, Job.job_id == AICandidateMatch.job_id)
            .join(CandidateProfile, CandidateProfile.candidate_id == AICandidateMatch.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .outerjoin(latest_resume, latest_resume.c.candidate_id == CandidateProfile.candidate_id)
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.generated_at == latest_resume.c.generated_at,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(
                AICandidateMatch.job_id == job_id,
                AICandidateMatch.candidate_id == candidate_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )
        return result.first()
