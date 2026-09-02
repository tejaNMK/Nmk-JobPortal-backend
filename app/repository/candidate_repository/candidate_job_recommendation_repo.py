from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.job_recommendation import JobRecommendation
from app.model.employer_model.job import Job
from app.model.master_data.candidate_target_role import CandidateTargetRole
from app.model.master_data.target_role import MasterTargetRole
from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.repository.employer_repository.job_repo import JobRepository
from app.service.candidate_job_recommendation_engine import (
    CandidateMatchContext,
    JobMatchContext,
)

# Upper bound on how many active jobs we pull into the Python scoring pass.
# Keeps the recommendation request bounded/predictable in latency even on a
# large job board; a future embeddings/ANN-backed engine can replace this
# coarse DB narrowing with a vector similarity pre-filter.
JOB_POOL_LIMIT = 500


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _extract_skill_list(skills_json) -> List[str]:
    if not skills_json:
        return []
    if isinstance(skills_json, dict):
        raw = skills_json.get("skills")
    elif isinstance(skills_json, list):
        raw = skills_json
    else:
        raw = None

    if not isinstance(raw, list):
        return []

    out: List[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("skill")
            if name:
                out.append(str(name))
    return out


class CandidateJobRecommendationRepo:
    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    async def get_candidate_profile(
        cls, session: AsyncSession, user_id: UUID
    ) -> Optional[CandidateProfile]:
        result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def _get_latest_resume_detail(
        cls, session: AsyncSession, candidate_id: str
    ) -> Optional[CandidateResumeDetail]:
        result = await session.execute(
            select(CandidateResumeDetail)
            .where(
                CandidateResumeDetail.candidate_id == candidate_id,
                CandidateResumeDetail.is_deleted.is_(False),
            )
            .order_by(CandidateResumeDetail.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_latest_resume_detail(
        cls, session: AsyncSession, candidate_id: str
    ) -> Optional[CandidateResumeDetail]:
        """Public accessor for the candidate's most recently generated
        resume detail (structured experience/education/skills JSON).

        Exposes the same query `build_candidate_match_context` uses
        internally, so other services (e.g. `JobMatchService` / AI Job
        Match Score) that need the raw resume detail -- not just the
        derived `CandidateMatchContext` -- can reuse this lookup instead
        of duplicating the query.
        """
        return await cls._get_latest_resume_detail(session, candidate_id)

    @classmethod
    async def _get_target_role_names(
        cls, session: AsyncSession, candidate_id: str
    ) -> List[str]:
        result = await session.execute(
            select(MasterTargetRole.name)
            .join(
                CandidateTargetRole,
                CandidateTargetRole.target_role_id == MasterTargetRole.target_role_id,
            )
            .where(CandidateTargetRole.candidate_id == candidate_id)
        )
        return [name for name in result.scalars().all() if name]

    @classmethod
    async def build_candidate_match_context(
        cls, session: AsyncSession, profile: CandidateProfile
    ) -> CandidateMatchContext:
        resume_detail = await cls._get_latest_resume_detail(session, profile.candidate_id)
        target_roles = await cls._get_target_role_names(session, profile.candidate_id)

        skills = set()
        for s in _extract_skill_list(resume_detail.skills_json if resume_detail else None):
            skills.add(s.strip().lower())
        if profile.skills_summary:
            for part in profile.skills_summary.replace(";", ",").split(","):
                part = part.strip()
                if part:
                    skills.add(part.lower())

        preferred_titles = set(target_roles)
        if profile.target_roles:
            for part in profile.target_roles.replace(";", ",").split(","):
                part = part.strip()
                if part:
                    preferred_titles.add(part)

        return CandidateMatchContext(
            skills=skills,
            total_experience_years=_to_float(profile.total_experience),
            headline=profile.headline,
            current_designation=profile.current_company,
            preferred_titles=preferred_titles,
            current_location=profile.current_location,
            preferred_location=profile.preferred_location,
            desired_employment_type=profile.desired_employment,
            work_preference=profile.work_preference,
            expected_salary_min=_to_float(profile.expected_ctc),
            expected_salary_max=_to_float(profile.expected_ctc),
            profile_completion_pct=profile.profile_completion_pct or 0,
        )

    @classmethod
    async def _get_applied_job_ids(
        cls, session: AsyncSession, candidate_id: str
    ) -> set[str]:
        result = await session.execute(
            select(JobApplication.job_id).where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
        )
        return set(result.scalars().all())

    @classmethod
    async def get_eligible_job_pool(
        cls,
        session: AsyncSession,
        candidate_id: str,
        *,
        exclude_applied: bool = True,
        limit: int = JOB_POOL_LIMIT,
    ) -> Tuple[List[Job], set[str]]:
        """Active, non-expired, non-deleted jobs the candidate hasn't applied
        to yet — the raw pool the scoring engine ranks."""

        now = cls._utc_now_naive()
        await JobRepository.expire_jobs_past_deadline(session=session, now=now)

        applied_job_ids: set[str] = set()
        if exclude_applied:
            applied_job_ids = await cls._get_applied_job_ids(session, candidate_id)

        conditions = [CandidateJobSearchRepo._active_job_predicate(now)]
        if applied_job_ids:
            conditions.append(Job.job_id.notin_(applied_job_ids))

        query = (
            select(Job)
            .where(*conditions)
            .options(selectinload(Job.skills))
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(query)).scalars().all()
        return list(rows), applied_job_ids

    @staticmethod
    def to_job_match_context(job: Job) -> JobMatchContext:
        skills = {s.skill.strip().lower() for s in (job.skills or []) if s.skill}
        return JobMatchContext(
            job_id=job.job_id,
            title=job.title or "",
            required_skills=skills,
            preferred_skills=set(),
            experience_min=job.experience_min,
            experience_max=job.experience_max,
            location=job.location,
            employment_type=job.employment_type,
            work_mode=job.work_mode,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
        )

    @classmethod
    async def upsert_recommendations(
        cls,
        session: AsyncSession,
        candidate_id: str,
        scored: Sequence[Tuple[str, float]],
    ) -> None:
        """Persist the current top matches to `job_recommendations` so the
        recommendation is auditable/cache-able, and stale rows for jobs that
        fell out of this candidate's top matches are cleared out."""

        job_ids = [job_id for job_id, _ in scored]

        # Drop previous recommendations that are no longer in the current
        # top set, then upsert the current set with fresh scores.
        if job_ids:
            await session.execute(
                delete(JobRecommendation).where(
                    JobRecommendation.candidate_id == candidate_id,
                    JobRecommendation.job_id.notin_(job_ids),
                )
            )
        else:
            await session.execute(
                delete(JobRecommendation).where(
                    JobRecommendation.candidate_id == candidate_id,
                )
            )
            await session.commit()
            return

        # There's no unique constraint on (candidate_id, job_id) in the base
        # model, so look up + update/insert explicitly rather than relying
        # on an ON CONFLICT upsert.
        for job_id, score in scored:
            existing = await session.execute(
                select(JobRecommendation).where(
                    JobRecommendation.candidate_id == candidate_id,
                    JobRecommendation.job_id == job_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.match_score = score
                row.generated_at = cls._utc_now_naive()
                session.add(row)
            else:
                session.add(
                    JobRecommendation(
                        candidate_id=candidate_id,
                        job_id=job_id,
                        match_score=score,
                        generated_at=cls._utc_now_naive(),
                    )
                )

        await session.commit()