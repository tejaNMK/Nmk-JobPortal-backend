from __future__ import annotations

import logging
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException

from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.job import Job
from app.repository.candidate_dashboard_repo import DashboardRepo
from app.utils.image_urls import resolve_profile_image_url
from app.service.candidate_job_recommendation_service import (
    CandidateJobRecommendationService,
)
from app.candidate_dashboard_schema import (
    ApplicationStatusCount,
    CandidateDashboardResponse,
    DashboardActivePackage,
    DashboardAppliedJob,
    DashboardApplicationStats,
    DashboardFollowedCompany,
    DashboardJobCard,
    DashboardProfileSummary,
    DashboardRecommendedJob,
    DashboardStatBar,
)

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession


_ALL_STATUSES = ["APPLIED", "REVIEW", "INTERVIEW", "OFFER", "REJECTED", "ARCHIVED", "WITHDRAWN"]


def _display_image_url(stored_value: Optional[str]) -> Optional[str]:
    return resolve_profile_image_url(stored_value)


def _format_salary(job: Job) -> Optional[str]:
    """
    Pre-formats the salary range for display, e.g. "USD5000 - USD6000/Monthly".
    Returns None when neither bound is set.
    """
    currency = job.salary_currency or "USD"
    period = job.salary_period or "Monthly"

    def _fmt(value) -> Optional[str]:
        if value is None:
            return None
        # Whole numbers render without a trailing ".0" (e.g. "USD5000" not "USD5000.0")
        as_int = int(value)
        return f"{currency}{as_int if as_int == value else value}"

    low = _fmt(job.salary_min)
    high = _fmt(job.salary_max)

    if low and high:
        return f"{low} - {high}/{period}"
    if low:
        return f"{low}/{period}"
    if high:
        return f"{high}/{period}"
    return None


def _build_job_card(job: Job, company_map: Dict[str, CompanyProfile]) -> DashboardJobCard:
    cp: Optional[CompanyProfile] = company_map.get(job.employer_id)
    return DashboardJobCard(
        job_id=job.job_id,
        title=job.title,
        location=job.location,
        work_mode=job.work_mode,
        badge=job.employment_type,
        salary=_format_salary(job),
        date=job.created_at,
        company=cp.company_name if cp else None,
        logo=cp.logo_path if cp else None,
        industry=cp.industry if cp else None,
    )


def _unique_employer_ids(jobs: List[Optional[Job]]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for j in jobs:
        if j and j.employer_id not in seen:
            seen.add(j.employer_id)
            out.append(j.employer_id)
    return out


def _open_to_work_label(open_to_work: bool) -> str:
    """
    Returns the UI subtitle shown under the 'Open to Work' toggle in the sidebar.
    When True  → "Visible to recruiters"   (green label in UI)
    When False → "Not visible to recruiters"
    """
    return "Visible to recruiters" if open_to_work else "Not visible to recruiters"


class CandidateDashboardService:

    @staticmethod
    async def get_dashboard(session: AsyncSession, user_id: UUID) -> CandidateDashboardResponse:
        profile, user = await DashboardRepo.fetch_profile_and_user(session, user_id)

        if not profile:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        candidate_id: str = profile.candidate_id

        # ── Stat bar counts ───────────────────────────────────────────────────
        cv_count = await DashboardRepo.fetch_cv_count(session, candidate_id)
        unread_msgs = await DashboardRepo.fetch_unread_message_count(session, user_id)
        profile_views = await DashboardRepo.fetch_profile_views_count(session, candidate_id)
        followings_count = await DashboardRepo.fetch_followings_count(session, candidate_id)

        # ── Applications ──────────────────────────────────────────────────────
        stats_rows = await DashboardRepo.fetch_application_stats(session, candidate_id)
        recent_apps = await DashboardRepo.fetch_recent_applications(session, candidate_id, limit=5)

        # ── Recommendations ───────────────────────────────────────────────────
        # `job_recommendations` is only a cache/audit table: rows are written
        # as a side effect of CandidateJobRecommendationService.get_recommended_jobs
        # (the AI-powered "/candidate/jobs/recommended" endpoint used by the
        # Job Listings page). A candidate who hasn't hit that endpoint yet has
        # no rows here at all, which made the dashboard's "Recommended Jobs"
        # panel appear empty even though recommendations work fine elsewhere.
        # Run the same scoring pipeline here so the dashboard is always
        # backed by fresh recommendations too, regardless of whether the
        # candidate has visited Job Listings yet.
        await CandidateJobRecommendationService.get_recommended_jobs(
            session, user_id, page=1, page_size=5
        )
        recommendations = await DashboardRepo.fetch_recommendations(session, candidate_id, limit=5)

        # ── Company map for job cards ─────────────────────────────────────────
        all_jobs = ([app.job for app in recent_apps] + [rec.job for rec in recommendations])
        employer_ids = _unique_employer_ids(all_jobs)
        company_map = await DashboardRepo.fetch_companies_by_employer_ids(session, employer_ids)

        # ── Followings ────────────────────────────────────────────────────────
        following_rows = await DashboardRepo.fetch_followings(session, candidate_id, limit=10)
        company_ids = [f.company_id for f in following_rows]
        open_jobs_map = await DashboardRepo.fetch_open_jobs_count_by_company(session, company_ids)

        # ── Assemble response ─────────────────────────────────────────────────

        # Stat Bar — four counter tiles at the top
        stat_bar = DashboardStatBar(
            profile_views=profile_views,
            followings=followings_count,
            cv_list=cv_count,
            messages=unread_msgs,
        )

        # Profile Summary — sidebar mini-card + main profile card
        full_name = " ".join(filter(None, [user.first_name, user.last_name]))
        profile_summary = DashboardProfileSummary(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            name=full_name,
            email=user.email,                               # identity line in sidebar
            phone=user.mobile_number,
            avatar=_display_image_url(user.profile_image_url),
            cover=_display_image_url(user.cover_image_url),  # banner on profile card
            location=profile.current_location,
            open_to_work=profile.open_to_work,
            open_to_work_label=_open_to_work_label(profile.open_to_work),  # sidebar subtitle
            profile_visibility=profile.profile_visibility,
            headline=profile.headline,
            profile_completion_pct=profile.profile_completion_pct,
            has_active_resume=bool(profile.active_resume_id),
        )

        # Application Stats — breakdown by status for charts / counters
        stats_by_status = {row[0]: row[1] for row in stats_rows}
        application_stats = DashboardApplicationStats(
            total=sum(stats_by_status.values()),
            breakdown=[
                ApplicationStatusCount(status=s, count=stats_by_status.get(s, 0))
                for s in _ALL_STATUSES
            ],
        )

        # Recent Applications — "My Applied Jobs" section (latest 5)
        recent_applications = [
            DashboardAppliedJob(
                application_id=app.application_id,
                application_status=app.application_status,
                applied=app.applied_at,
                job=_build_job_card(app.job, company_map),
            )
            for app in recent_apps
        ]

        # Active Package — "Active Package Details" section (None if no active package)
        active_package: Optional[DashboardActivePackage] = None

        # Job Recommendations — "Recommended Jobs" section (top 5 by match score)
        job_recommendations = [
            DashboardRecommendedJob(
                recommendation_id=rec.recommendation_id,
                match_score=rec.match_score,
                generated_at=rec.generated_at,
                job=_build_job_card(rec.job, company_map),
            )
            for rec in recommendations
        ]

        # Followings — "My Followings" section (latest 10 followed companies)
        followings = [
            DashboardFollowedCompany(
                company_id=f.company_id,
                name=f.company.company_name if f.company else "",
                industry=f.company.industry if f.company else None,
                location=f.company.location if f.company else None,
                logo=f.company.logo_path if f.company else None,
                jobs=open_jobs_map.get(f.company_id, 0),
            )
            for f in following_rows
            if f.company
        ]

        return CandidateDashboardResponse(
            stat_bar=stat_bar,
            profile_summary=profile_summary,
            application_stats=application_stats,
            recent_applications=recent_applications,
            active_package=active_package,
            job_recommendations=job_recommendations,
            followings=followings,
        )
