from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from app.utils.utc import utc_now_naive

from sqlalchemy import asc, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.job import Job

OPEN_JOB_STATUSES = ("PUBLISHED",)


class CandidateFollowingRepo:

    # ── Candidate resolution ────────────────────────────────────────────────
    @classmethod
    async def get_candidate_profile(cls, session: AsyncSession, user_id) -> Optional[CandidateProfile]:
        result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    # ── Company lookup ──────────────────────────────────────────────────────
    @classmethod
    async def get_public_company(cls, session: AsyncSession, company_id: str) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(
                CompanyProfile.company_id == company_id,
                CompanyProfile.is_public.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ── Follow / unfollow ────────────────────────────────────────────────────
    @classmethod
    async def get_following_row(
        cls, session: AsyncSession, candidate_id: str, company_id: str
    ) -> Optional[CandidateCompanyFollowing]:
        """Returns the row regardless of is_deleted, so callers can resurrect it."""
        result = await session.execute(
            select(CandidateCompanyFollowing).where(
                CandidateCompanyFollowing.candidate_id == candidate_id,
                CandidateCompanyFollowing.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def create_following(
        cls, session: AsyncSession, candidate_id: str, company_id: str
    ) -> CandidateCompanyFollowing:
        row = CandidateCompanyFollowing(candidate_id=candidate_id, company_id=company_id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @classmethod
    async def restore_following(cls, session: AsyncSession, row: CandidateCompanyFollowing) -> CandidateCompanyFollowing:
        row.is_deleted = False
        row.deleted_at = None
        row.followed_at = utc_now_naive()
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @classmethod
    async def soft_delete_following(cls, session: AsyncSession, row: CandidateCompanyFollowing) -> None:
        row.is_deleted = True
        row.deleted_at = utc_now_naive()
        session.add(row)
        await session.commit()

    # ── Listing ──────────────────────────────────────────────────────────────
    @classmethod
    async def list_followed(
        cls,
        session: AsyncSession,
        candidate_id: str,
        search: Optional[str],
        sort_by: str,
        page: int,
        page_size: int,
    ) -> Tuple[List[CandidateCompanyFollowing], int]:
        conditions = [
            CandidateCompanyFollowing.candidate_id == candidate_id,
            CandidateCompanyFollowing.is_deleted.is_(False),
        ]

        base_query = (
            select(CandidateCompanyFollowing)
            .join(CompanyProfile, CompanyProfile.company_id == CandidateCompanyFollowing.company_id)
            .where(*conditions)
        )

        if search:
            like = f"%{search.strip()}%"
            base_query = base_query.where(
                or_(
                    CompanyProfile.company_name.ilike(like),
                    CompanyProfile.industry.ilike(like),
                )
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await session.execute(count_query)).scalar_one() or 0

        sort_map = {
            "FOLLOWED_DATE_DESC": desc(CandidateCompanyFollowing.followed_at),
            "FOLLOWED_DATE_ASC": asc(CandidateCompanyFollowing.followed_at),
            "NAME_ASC": asc(CompanyProfile.company_name),
            "NAME_DESC": desc(CompanyProfile.company_name),
        }
        order_clause = sort_map.get(sort_by, desc(CandidateCompanyFollowing.followed_at))

        rows_query = (
            base_query.options(selectinload(CandidateCompanyFollowing.company))
            .order_by(order_clause)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(rows_query)).scalars().all()
        return list(rows), total

    @classmethod
    async def list_followed_company_ids(cls, session: AsyncSession, candidate_id: str) -> List[str]:
        result = await session.execute(
            select(CandidateCompanyFollowing.company_id).where(
                CandidateCompanyFollowing.candidate_id == candidate_id,
                CandidateCompanyFollowing.is_deleted.is_(False),
            )
        )
        return [row[0] for row in result.all()]

    # ── Open job counts ──────────────────────────────────────────────────────
    @classmethod
    async def fetch_open_jobs_count_by_company(
        cls, session: AsyncSession, company_ids: Sequence[str]
    ) -> Dict[str, int]:
        if not company_ids:
            return {}
        rows = await session.execute(
            select(
                CompanyProfile.company_id,
                func.count(Job.job_id).label("cnt"),
            )
            .join(Job, Job.employer_id == CompanyProfile.employer_id)
            .where(
                CompanyProfile.company_id.in_(company_ids),
                Job.status.in_(OPEN_JOB_STATUSES),
                Job.closed_at.is_(None),
                Job.is_deleted.is_(False),
            )
            .group_by(CompanyProfile.company_id)
        )
        return {row.company_id: row.cnt for row in rows.all()}

    # ── Smart suggestions signals ───────────────────────────────────────────
    @classmethod
    async def fetch_top_candidate_job_title(cls, session: AsyncSession, candidate_id: str) -> Optional[str]:
        """Most common job title across the candidate's saved jobs + applications,
        used to seed the 'Companies hiring for <role> roles' suggestion."""
        result = await session.execute(
            select(Job.title, func.count().label("cnt"))
            .select_from(CandidateSavedJob)
            .join(Job, Job.job_id == CandidateSavedJob.job_id)
            .where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.saved_flag.is_(True),
                CandidateSavedJob.deleted_at.is_(None),
            )
            .group_by(Job.title)
            .order_by(desc("cnt"))
            .limit(1)
        )
        row = result.first()
        if row:
            return row[0]

        result = await session.execute(
            select(Job.title, func.count().label("cnt"))
            .select_from(JobApplication)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .group_by(Job.title)
            .order_by(desc("cnt"))
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None

    @classmethod
    async def fetch_companies_hiring_for_title(
        cls,
        session: AsyncSession,
        title: str,
        exclude_company_ids: Sequence[str],
        limit: int = 6,
    ) -> List[CompanyProfile]:
        query = (
            select(CompanyProfile)
            .join(Job, Job.employer_id == CompanyProfile.employer_id)
            .where(
                CompanyProfile.is_public.is_(True),
                Job.title.ilike(f"%{title}%"),
                Job.status.in_(OPEN_JOB_STATUSES),
                Job.closed_at.is_(None),
                Job.is_deleted.is_(False),
            )
        )
        if exclude_company_ids:
            query = query.where(CompanyProfile.company_id.notin_(exclude_company_ids))
        query = query.group_by(CompanyProfile.company_id).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def fetch_companies_expanding_remote(
        cls,
        session: AsyncSession,
        exclude_company_ids: Sequence[str],
        limit: int = 6,
        min_open_roles: int = 2,
    ) -> List[CompanyProfile]:
        """Companies with several concurrent remote openings — surfaced under
        'Studios expanding remote design teams'."""
        query = (
            select(CompanyProfile, func.count(Job.job_id).label("cnt"))
            .join(Job, Job.employer_id == CompanyProfile.employer_id)
            .where(
                CompanyProfile.is_public.is_(True),
                Job.work_mode == "REMOTE",
                Job.status.in_(OPEN_JOB_STATUSES),
                Job.closed_at.is_(None),
                Job.is_deleted.is_(False),
            )
        )
        if exclude_company_ids:
            query = query.where(CompanyProfile.company_id.notin_(exclude_company_ids))
        query = (
            query.group_by(CompanyProfile.company_id)
            .having(func.count(Job.job_id) >= min_open_roles)
            .order_by(desc("cnt"))
            .limit(limit)
        )
        result = await session.execute(query)
        return [row[0] for row in result.all()]

    @classmethod
    async def fetch_companies_by_ids(cls, session: AsyncSession, company_ids: Sequence[str]) -> List[CompanyProfile]:
        if not company_ids:
            return []
        result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.company_id.in_(company_ids))
        )
        return list(result.scalars().all())

    # ── Notify preference ────────────────────────────────────────────────────
    @classmethod
    async def set_notify_preference(
        cls, session: AsyncSession, profile: CandidateProfile, enabled: bool
    ) -> CandidateProfile:
        profile.follow_notifications_enabled = enabled
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile
