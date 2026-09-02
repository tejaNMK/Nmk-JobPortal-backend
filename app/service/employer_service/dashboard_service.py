from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterable, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.employer_dashboard_schema import (
    EmployerAnalyticsApplicationAnalytics,
    EmployerAnalyticsCandidateAnalytics,
    EmployerAnalyticsCandidateSource,
    EmployerAnalyticsChartSeries,
    EmployerAnalyticsCharts,
    EmployerAnalyticsDistributionPoint,
    EmployerAnalyticsFilterOptions,
    EmployerAnalyticsFilters,
    EmployerAnalyticsFunnelStage,
    EmployerAnalyticsInterviewAnalytics,
    EmployerAnalyticsJobDetail,
    EmployerAnalyticsJobOption,
    EmployerAnalyticsJobPerformance,
    EmployerAnalyticsOverview,
    EmployerAnalyticsResponse,
    EmployerAnalyticsTrendPoint,
    EmployerAnalyticsTopJob,
    EmployerDashboardApplicationStatusCount,
    EmployerDashboardCandidateSummary,
    EmployerDashboardCompanySummary,
    EmployerDashboardFilterOptions,
    EmployerDashboardFilters,
    EmployerDashboardInterview,
    EmployerDashboardJobStageAnalytics,
    EmployerDashboardJobStatusCount,
    EmployerDashboardJobSummary,
    EmployerDashboardJobTableRow,
    EmployerDashboardPackageSummary,
    EmployerDashboardRecentActivity,
    EmployerDashboardRecentApplication,
    EmployerDashboardResponse,
    EmployerDashboardStageCount,
    EmployerDashboardStageTransition,
    EmployerDashboardStatCard,
    EmployerDashboardStats,
    EmployerDashboardTimeSeriesPoint,
)
from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.interview import Interview
from app.model.employer_model.job import Job
from app.model.employer_model.job_posting_audit import JobPostingAudit
from app.repository.employer_repository.dashboard_repo import EmployerDashboardRepo
from app.repository.employer_repository.job_repo import JobRepository
from app.utils.job_time import utc_now_naive
from app.utils.activity_mapper import build_recent_activity, unpack_activity_row
from app.utils.image_urls import resolve_profile_image_url


_APPLICATION_STATUSES = ["APPLIED", "REVIEW", "SHORTLISTED", "INTERVIEW", "OFFER", "REJECTED", "ARCHIVED", "WITHDRAWN"]
_JOB_STATUSES = ["DRAFT", "PUBLISHED", "CLOSED", "EXPIRED", "PAUSED", "ARCHIVED"]
_EMPLOYER_ROLE_CODES = {"ROLE_EMPLOYER", "ROLE_RECRUITER", "ROLE_ADMIN"}
_ANALYTICS_FUNNEL = [
    ("APPLIED", "Applied", {"APPLIED"}),
    ("SCREENING", "Screening", {"REVIEW", "REVIEWED", "SCREENING"}),
    ("SHORTLISTED", "Shortlisted", {"SHORTLISTED"}),
    ("INTERVIEW", "Interview", {"INTERVIEW", "INTERVIEW_SCHEDULED", "INTERVIEWED", "INTERVIEW_ROUND_1", "INTERVIEW_ROUND_2", "HR_ROUND"}),
    ("OFFERED", "Offered", {"OFFER", "OFFERED", "HIRED"}),
]
_PIPELINE_STAGES = [
    ("APPLIED", "Applied", {"APPLIED"}),
    ("SCREENING", "Screening", {"REVIEW", "REVIEWED", "SCREENING"}),
    ("SHORTLISTED", "Shortlisted", {"SHORTLISTED"}),
    ("ASSESSMENT", "Assessment", {"ASSESSMENT"}),
    ("INTERVIEW_ROUND_1", "Interview Round 1", {"INTERVIEW_ROUND_1"}),
    ("INTERVIEW_ROUND_2", "Interview Round 2", {"INTERVIEW_ROUND_2"}),
    ("HR_ROUND", "HR Round", {"HR_ROUND"}),
    ("SELECTED", "Selected", {"SELECTED"}),
    ("OFFERED", "Offered", {"OFFER", "OFFERED"}),
    ("ACCEPTED", "Accepted", {"ACCEPTED", "HIRED"}),
    ("REJECTED", "Rejected", {"REJECTED"}),
    ("WITHDRAWN", "Withdrawn", {"WITHDRAWN"}),
]
_ANALYTICS_STAGE_RANKS = {
    status: rank
    for rank, (_, _, statuses) in enumerate(_ANALYTICS_FUNNEL)
    for status in statuses
}


def _role_codes(payload: dict) -> set[str]:
    roles = payload.get("roles") or []
    return {
        str(role.get("role_code"))
        for role in roles
        if isinstance(role, dict) and role.get("role_code")
    }


def _full_name(user: Optional[Users]) -> str:
    if not user:
        return "Unknown Candidate"
    name = " ".join(filter(None, [user.first_name, user.last_name])).strip()
    return name or user.email or "Unknown Candidate"


def _candidate_summary(
    candidate: CandidateProfile,
    user: Optional[Users],
) -> EmployerDashboardCandidateSummary:
    total_experience = candidate.total_experience
    if isinstance(total_experience, Decimal):
        total_experience = float(total_experience)
    return EmployerDashboardCandidateSummary(
        candidate_id=candidate.candidate_id,
        user_id=str(candidate.user_id) if candidate.user_id else None,
        full_name=_full_name(user),
        email=user.email if user else None,
        phone_number=user.mobile_number if user else None,
        headline=candidate.headline,
        current_location=candidate.current_location,
        total_experience=total_experience,
        profile_image_url=resolve_profile_image_url(user.profile_image_url if user else None),
    )


def _job_summary(job: Job) -> EmployerDashboardJobSummary:
    return EmployerDashboardJobSummary(
        job_id=job.job_id,
        title=job.title,
        status=job.status,
        location=job.location,
        employment_type=job.employment_type,
        work_mode=job.work_mode,
        posted_at=job.created_at,
        application_deadline=job.application_deadline,
    )


def _counts_by_key(rows: Iterable[tuple[str, int]]) -> dict[str, int]:
    return {str(status): int(count or 0) for status, count in rows}


def _ordered_statuses(statuses: Iterable[str]) -> list[str]:
    status_set = {str(status) for status in statuses if status}
    ordered = [status for status in _APPLICATION_STATUSES if status in status_set]
    ordered.extend(sorted(status_set.difference(_APPLICATION_STATUSES)))
    return ordered


def _coerce_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _interview_scheduled_at(interview: Interview) -> Optional[datetime]:
    scheduled_at = getattr(interview, "scheduled_at", None)
    if scheduled_at is not None:
        return scheduled_at
    interview_date = getattr(interview, "interview_date", None)
    interview_time = getattr(interview, "interview_time", None)
    if interview_date and interview_time:
        return datetime.combine(interview_date, interview_time)
    return None


def _interview_location_or_link(interview: Interview) -> Optional[str]:
    location_or_link = getattr(interview, "location_or_link", None)
    if location_or_link:
        return location_or_link
    return getattr(interview, "meeting_link", None) or getattr(
        interview,
        "interview_location",
        None,
    )


class EmployerDashboardService:
    @staticmethod
    async def get_analytics(
        session: AsyncSession,
        payload: dict,
        filters: EmployerAnalyticsFilters,
    ) -> EmployerAnalyticsResponse:
        user_id = EmployerDashboardService._get_authorized_user_id(payload)
        date_from, date_to = EmployerDashboardService._resolve_analytics_dates(filters)

        employer = await EmployerDashboardRepo.fetch_employer_profile(session, user_id)
        if not employer:
            raise HTTPException(status_code=403, detail="Employer profile not found")

        employer_id = str(employer.id)
        if hasattr(session, "execute"):
            await JobRepository.expire_jobs_past_deadline(
                session=session,
                now=utc_now_naive(),
                employer_id=employer_id,
            )

        dashboard_filters = EmployerDashboardFilters(
            job_id=filters.job_id,
            date_from=date_from,
            date_to=date_to,
            limit=10,
        )
        for key in ("department", "employment_type", "location", "hiring_manager", "status"):
            setattr(dashboard_filters, key, getattr(filters, key, None))
        filter_jobs = await EmployerDashboardRepo.fetch_job_filter_options(
            session=session,
            employer_id=employer_id,
        )
        stat_counts = await EmployerDashboardRepo.fetch_analytics_stat_counts(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        applications_over_time_rows = await EmployerDashboardRepo.fetch_applications_over_time(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        stage_events = await EmployerDashboardRepo.fetch_analytics_stage_events(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        source_rows = await EmployerDashboardRepo.fetch_analytics_candidate_sources(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        top_job_rows = await EmployerDashboardRepo.fetch_analytics_top_jobs(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
            limit=10,
        )
        hire_milestones = await EmployerDashboardRepo.fetch_analytics_hire_milestones(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        overview_counts = await EmployerDashboardRepo.fetch_analytics_overview_counts(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        job_rows = await EmployerDashboardRepo.fetch_analytics_job_rows(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        application_events = await EmployerDashboardRepo.fetch_analytics_application_events(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        interview_events = await EmployerDashboardRepo.fetch_analytics_interview_events(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        candidate_rows = await EmployerDashboardRepo.fetch_analytics_candidate_rows(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        milestone_rows = await EmployerDashboardRepo.fetch_analytics_application_milestones(
            session=session,
            employer_id=employer_id,
            filters=dashboard_filters,
        )
        hiring_funnel = EmployerDashboardService._build_hiring_funnel(stage_events)
        job_analytics = EmployerDashboardService._build_job_analytics(job_rows, milestone_rows)
        application_analytics = EmployerDashboardService._build_application_analytics(
            application_events,
            date_from,
            date_to,
            filters.period,
        )
        hiring_pipeline = EmployerDashboardService._build_hiring_pipeline(stage_events)
        interview_analytics = EmployerDashboardService._build_interview_analytics(interview_events)
        candidate_analytics = EmployerDashboardService._build_candidate_analytics(candidate_rows)
        job_performance = EmployerDashboardService._build_job_performance(job_analytics)
        shortlisted_stage = next(
            (stage for stage in hiring_funnel if stage.stage == "SHORTLISTED"),
            None,
        )
        if shortlisted_stage:
            stat_counts = {**stat_counts, "shortlisted": shortlisted_stage.count}

        stat_cards = EmployerDashboardService._build_analytics_stat_cards(
            counts=stat_counts,
            avg_time_to_hire_days=EmployerDashboardService._average_days(hire_milestones),
        )

        return EmployerAnalyticsResponse(
            filter_options=EmployerAnalyticsFilterOptions(
                jobs=[
                    EmployerAnalyticsJobOption(job_id=job.job_id, title=job.title)
                    for job in filter_jobs
                ],
            ),
            stat_cards=stat_cards,
            applications_over_time=EmployerDashboardService._fill_applications_over_time(
                applications_over_time_rows,
                date_from,
                date_to,
            ),
            hiring_funnel=hiring_funnel,
            candidate_source=EmployerDashboardService._build_candidate_sources(source_rows),
            top_jobs=[
                EmployerDashboardService._build_analytics_top_job(row)
                for row in top_job_rows
            ],
            overview_metrics=EmployerAnalyticsOverview(**overview_counts),
            job_analytics=job_analytics,
            application_analytics=application_analytics,
            hiring_pipeline=hiring_pipeline,
            interview_analytics=interview_analytics,
            candidate_analytics=candidate_analytics,
            job_performance=job_performance,
            chart_data=EmployerDashboardService._build_chart_data(
                application_analytics=application_analytics,
                hiring_pipeline=hiring_pipeline,
                candidate_analytics=candidate_analytics,
                job_analytics=job_analytics,
            ),
        )

    @staticmethod
    async def get_dashboard(
        session: AsyncSession,
        payload: dict,
        filters: EmployerDashboardFilters,
    ) -> EmployerDashboardResponse:
        user_id = EmployerDashboardService._get_authorized_user_id(payload)

        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise HTTPException(status_code=400, detail="date_from cannot be after date_to")

        employer = await EmployerDashboardRepo.fetch_employer_profile(session, user_id)
        if not employer:
            raise HTTPException(status_code=403, detail="Employer profile not found")

        employer_id = str(employer.id)
        company = await EmployerDashboardRepo.fetch_company_profile(session, employer_id)
        if hasattr(session, "execute"):
            await JobRepository.expire_jobs_past_deadline(
                session=session,
                now=utc_now_naive(),
                employer_id=employer_id,
            )

        stat_counts = await EmployerDashboardRepo.fetch_stat_counts(
            session=session,
            employer_id=employer_id,
            receiver_user_id=user_id,
        )
        application_status_rows = await EmployerDashboardRepo.fetch_application_status_counts(
            session=session,
            employer_id=employer_id,
            filters=filters,
        )
        job_status_rows = await EmployerDashboardRepo.fetch_job_status_counts(
            session=session,
            employer_id=employer_id,
        )
        applications_over_time_rows = await EmployerDashboardRepo.fetch_applications_over_time(
            session=session,
            employer_id=employer_id,
            filters=filters,
        )
        job_stage_rows = await EmployerDashboardRepo.fetch_job_stage_counts(
            session=session,
            employer_id=employer_id,
            filters=filters,
        )
        stage_transition_rows = await EmployerDashboardRepo.fetch_job_stage_transition_counts(
            session=session,
            employer_id=employer_id,
            filters=filters,
        )
        recent_application_rows = await EmployerDashboardRepo.fetch_recent_applications(
            session=session,
            employer_id=employer_id,
            filters=filters,
        )
        active_job_rows = await EmployerDashboardRepo.fetch_active_jobs(
            session=session,
            employer_id=employer_id,
            limit=filters.limit,
        )
        interview_rows = await EmployerDashboardRepo.fetch_upcoming_interviews(
            session=session,
            employer_id=employer_id,
            limit=filters.limit,
        )
        activity_rows = await EmployerDashboardRepo.fetch_recent_activity(
            session=session,
            employer_id=employer_id,
            limit=filters.limit,
        )
        filter_jobs = await EmployerDashboardRepo.fetch_job_filter_options(
            session=session,
            employer_id=employer_id,
        )

        company_summary = EmployerDashboardService._build_company_summary(employer, company)
        stat_cards = EmployerDashboardService._build_stat_cards(stat_counts)
        statistics = EmployerDashboardService._build_statistics(
            application_status_rows,
            job_status_rows,
            applications_over_time_rows,
        )

        return EmployerDashboardResponse(
            company_summary=company_summary,
            filters=filters,
            filter_options=EmployerDashboardFilterOptions(
                statuses=_ordered_statuses(
                    [
                        *[status for status, _ in application_status_rows],
                        *[
                            status
                            for _, status, _ in job_stage_rows
                        ],
                        *[
                            status
                            for _, from_status, to_status, _ in stage_transition_rows
                            for status in (from_status, to_status)
                            if status
                        ],
                        *_APPLICATION_STATUSES,
                    ]
                ),
                jobs=[_job_summary(job) for job in filter_jobs],
            ),
            stat_cards=stat_cards,
            statistics=statistics,
            recent_applications=[
                EmployerDashboardService._build_application_row(row)
                for row in recent_application_rows
            ],
            active_jobs=[
                EmployerDashboardService._build_job_table_row(row)
                for row in active_job_rows
            ],
            job_stage_analytics=EmployerDashboardService._build_job_stage_analytics(
                job_stage_rows,
                stage_transition_rows,
            ),
            upcoming_interviews=[
                EmployerDashboardService._build_interview_row(row)
                for row in interview_rows
            ],
            recent_activity=[
                EmployerDashboardService._build_activity_row(row)
                for row in activity_rows
            ],
            package_summary=EmployerDashboardPackageSummary(
                posted_jobs_used=stat_counts["total_jobs"]
            ),
        )

    @staticmethod
    def _get_authorized_user_id(payload: dict) -> UUID:
        raw_user_id = payload.get("user_id")
        if not raw_user_id:
            raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")

        role_codes = _role_codes(payload)
        if role_codes and role_codes.isdisjoint(_EMPLOYER_ROLE_CODES):
            raise HTTPException(status_code=403, detail="Only employers can access employer dashboard")
        return UUID(str(raw_user_id))

    @staticmethod
    def _resolve_analytics_dates(filters: EmployerAnalyticsFilters) -> tuple[date, date]:
        date_to = filters.to_date or date.today()
        date_from = filters.from_date or (date_to - timedelta(days=30))
        if date_from > date_to:
            raise HTTPException(status_code=400, detail="from_date cannot be after to_date")
        return date_from, date_to

    @staticmethod
    def _build_analytics_stat_cards(
        counts: dict[str, int],
        avg_time_to_hire_days: int,
    ) -> List[EmployerDashboardStatCard]:
        return [
            EmployerDashboardStatCard(
                key="active_jobs",
                label="Active Jobs",
                value=counts["active_jobs"],
                formatted_value=EmployerDashboardService._format_number(counts["active_jobs"]),
            ),
            EmployerDashboardStatCard(
                key="applications",
                label="Applications",
                value=counts["applications"],
                formatted_value=EmployerDashboardService._format_number(counts["applications"]),
            ),
            EmployerDashboardStatCard(
                key="shortlisted",
                label="Shortlisted",
                value=counts["shortlisted"],
                formatted_value=EmployerDashboardService._format_number(counts["shortlisted"]),
            ),
            EmployerDashboardStatCard(
                key="interviews",
                label="Interviews",
                value=counts["interviews"],
                formatted_value=EmployerDashboardService._format_number(counts["interviews"]),
            ),
            EmployerDashboardStatCard(
                key="avg_time_to_hire_days",
                label="Avg. Time to Hire",
                value=avg_time_to_hire_days,
                formatted_value=EmployerDashboardService._format_number(avg_time_to_hire_days),
            ),
            EmployerDashboardStatCard(
                key="profile_views",
                label="Profile Views",
                value=counts["profile_views"],
                formatted_value=EmployerDashboardService._format_number(counts["profile_views"]),
            ),
        ]

    @staticmethod
    def _fill_applications_over_time(rows, date_from: date, date_to: date) -> list[EmployerDashboardTimeSeriesPoint]:
        counts = {
            _coerce_date(applied_date): int(count or 0)
            for applied_date, count in rows
        }
        days = (date_to - date_from).days
        return [
            EmployerDashboardTimeSeriesPoint(
                date=date_from + timedelta(days=offset),
                applications=counts.get(date_from + timedelta(days=offset), 0),
            )
            for offset in range(days + 1)
        ]

    @staticmethod
    def _build_hiring_funnel(stage_events) -> list[EmployerAnalyticsFunnelStage]:
        highest_by_application: dict[str, int] = {}
        for application_id, raw_stage in stage_events:
            rank = _ANALYTICS_STAGE_RANKS.get(str(raw_stage))
            if rank is None:
                continue
            highest_by_application[str(application_id)] = max(
                highest_by_application.get(str(application_id), -1),
                rank,
            )

        return [
            EmployerAnalyticsFunnelStage(
                stage=stage,
                label=label,
                count=sum(1 for rank in highest_by_application.values() if rank >= index),
            )
            for index, (stage, label, _) in enumerate(_ANALYTICS_FUNNEL)
        ]

    @staticmethod
    def _build_candidate_sources(rows) -> list[EmployerAnalyticsCandidateSource]:
        total = sum(int(count or 0) for _, count in rows)
        if total <= 0:
            return []

        sources: list[EmployerAnalyticsCandidateSource] = []
        running_percent = 0
        for index, (source, count) in enumerate(rows):
            if index == len(rows) - 1:
                percent = max(0, 100 - running_percent)
            else:
                percent = round((int(count or 0) / total) * 100)
                running_percent += percent
            sources.append(
                EmployerAnalyticsCandidateSource(
                    source=str(source),
                    label=str(source).replace("_", " ").title(),
                    percent=percent,
                )
            )
        return sources

    @staticmethod
    def _build_analytics_top_job(row) -> EmployerAnalyticsTopJob:
        job, applications_count, shortlisted_count, view_count = row
        applications = int(applications_count or 0)
        shortlisted = int(shortlisted_count or 0)
        return EmployerAnalyticsTopJob(
            job_id=job.job_id,
            title=job.title,
            status=job.status,
            applications=applications,
            views=int(view_count or 0),
            conversion_rate=round((shortlisted / applications) * 100, 1) if applications else 0,
        )

    @staticmethod
    def _build_job_analytics(job_rows, milestone_rows) -> list[EmployerAnalyticsJobDetail]:
        milestones_by_job: dict[str, list[tuple[datetime, Optional[datetime], Optional[datetime], Optional[datetime]]]] = defaultdict(list)
        by_application: dict[str, dict[str, Any]] = {}
        for application_id, job_id, applied_at, status, changed_at in milestone_rows:
            item = by_application.setdefault(
                str(application_id),
                {
                    "job_id": str(job_id),
                    "applied_at": applied_at,
                    "first_response_at": None,
                    "shortlisted_at": None,
                    "hire_at": None,
                },
            )
            if status and changed_at:
                normalized = str(status).upper()
                if item["first_response_at"] is None:
                    item["first_response_at"] = changed_at
                if normalized in {"SHORTLISTED", "INTERVIEW", "INTERVIEWED", "OFFER", "OFFERED", "HIRED"}:
                    item["shortlisted_at"] = min(
                        [value for value in (item["shortlisted_at"], changed_at) if value]
                    )
                if normalized in {"HIRED", "ACCEPTED"}:
                    item["hire_at"] = min(
                        [value for value in (item["hire_at"], changed_at) if value]
                    )

        for item in by_application.values():
            milestones_by_job[item["job_id"]].append(
                (
                    item["applied_at"],
                    item["shortlisted_at"],
                    item["hire_at"],
                    item["first_response_at"],
                )
            )

        details: list[EmployerAnalyticsJobDetail] = []
        for row in job_rows:
            job, views, applications, interviewed, shortlisted, rejected, offers, hired = row
            applications = int(applications or 0)
            hired = int(hired or 0)
            milestones = milestones_by_job.get(str(job.job_id), [])
            details.append(
                EmployerAnalyticsJobDetail(
                    job_id=job.job_id,
                    title=job.title,
                    status=job.status,
                    posted_date=job.created_at,
                    expiry_date=job.application_deadline,
                    views=int(views or 0),
                    unique_views=int(views or 0),
                    applications=applications,
                    shortlisted=int(shortlisted or 0),
                    rejected=int(rejected or 0),
                    interviewed=int(interviewed or 0),
                    offers=int(offers or 0),
                    hired=hired,
                    conversion_rate=round((hired / applications) * 100, 1) if applications else 0,
                    average_time_to_hire=EmployerDashboardService._average_duration_days(
                        (applied_at, hire_at) for applied_at, _, hire_at, _ in milestones
                    ),
                    average_time_to_shortlist=EmployerDashboardService._average_duration_days(
                        (applied_at, shortlist_at) for applied_at, shortlist_at, _, _ in milestones
                    ),
                    average_response_time=EmployerDashboardService._average_duration_days(
                        (applied_at, response_at) for applied_at, _, _, response_at in milestones
                    ),
                )
            )
        return details

    @staticmethod
    def _build_application_analytics(
        application_events,
        date_from: date,
        date_to: date,
        selected_period: str,
    ) -> EmployerAnalyticsApplicationAnalytics:
        events = [
            {
                "applied_at": applied_at,
                "source": source or "UNKNOWN",
                "status": status or "UNKNOWN",
            }
            for _, applied_at, source, status in application_events
            if applied_at
        ]
        daily = EmployerDashboardService._bucket_application_events(events, "daily", date_from, date_to)
        weekly = EmployerDashboardService._bucket_application_events(events, "weekly", date_from, date_to)
        monthly = EmployerDashboardService._bucket_application_events(events, "monthly", date_from, date_to)
        yearly = EmployerDashboardService._bucket_application_events(events, "yearly", date_from, date_to)
        return EmployerAnalyticsApplicationAnalytics(
            daily_applications=daily,
            weekly_applications=weekly,
            monthly_applications=monthly,
            yearly_applications=yearly,
            application_sources=EmployerDashboardService._distribution(
                Counter(event["source"] for event in events)
            ),
            application_trends={
                "daily": daily,
                "weekly": weekly,
                "monthly": monthly,
                "yearly": yearly,
            }.get(selected_period, daily),
            application_status_distribution=EmployerDashboardService._distribution(
                Counter(event["status"] for event in events)
            ),
        )

    @staticmethod
    def _build_hiring_pipeline(stage_events) -> list[EmployerAnalyticsDistributionPoint]:
        current = Counter(str(stage or "").upper() for _, stage in stage_events if stage)
        counts = Counter()
        for stage_key, _, statuses in _PIPELINE_STAGES:
            counts[stage_key] = sum(current[status] for status in statuses)
        total = sum(counts.values())
        return [
            EmployerAnalyticsDistributionPoint(
                key=key,
                label=label,
                count=int(counts[key] or 0),
                percent=round((counts[key] / total) * 100, 1) if total else 0,
            )
            for key, label, _ in _PIPELINE_STAGES
        ]

    @staticmethod
    def _build_interview_analytics(interviews) -> EmployerAnalyticsInterviewAnalytics:
        today = date.today()
        counts = Counter(str(interview.status or "").upper() for interview in interviews)
        completed = int(counts["COMPLETED"])
        cancelled = int(counts["CANCELLED"])
        scheduled = int(counts["SCHEDULED"])
        rescheduled = int(counts["RESCHEDULED"])
        upcoming = sum(
            1
            for interview in interviews
            if str(interview.status or "").upper() == "SCHEDULED"
            and getattr(interview, "interview_date", None)
            and interview.interview_date >= today
        )
        today_count = sum(
            1
            for interview in interviews
            if getattr(interview, "interview_date", None) == today
        )
        durations = []
        for interview in interviews:
            start = getattr(interview, "interview_time", None)
            end = getattr(interview, "end_time", None)
            if start and end:
                start_minutes = start.hour * 60 + start.minute
                end_minutes = end.hour * 60 + end.minute
                if end_minutes > start_minutes:
                    durations.append(end_minutes - start_minutes)
        terminal = completed + cancelled
        return EmployerAnalyticsInterviewAnalytics(
            scheduled=scheduled,
            completed=completed,
            cancelled=cancelled,
            rescheduled=rescheduled,
            upcoming=upcoming,
            todays_interviews=today_count,
            success_rate=round((completed / terminal) * 100, 1) if terminal else 0,
            average_interview_duration=round(sum(durations) / len(durations), 1) if durations else 0,
        )

    @staticmethod
    def _build_candidate_analytics(candidate_rows) -> EmployerAnalyticsCandidateAnalytics:
        profiles_by_id: dict[str, Any] = {}
        resume_details_by_candidate: dict[str, list[Any]] = defaultdict(list)
        for profile, resume_detail in candidate_rows:
            profiles_by_id[str(profile.candidate_id)] = profile
            if resume_detail:
                resume_details_by_candidate[str(profile.candidate_id)].append(resume_detail)

        skill_counts = Counter()
        education_counts = Counter()
        location_counts = Counter()
        experience_counts = Counter()
        notice_counts = Counter()
        freshers = experienced = open_to_work = 0

        for candidate_id, profile in profiles_by_id.items():
            experience = float(profile.total_experience or 0)
            if experience <= 0:
                freshers += 1
            else:
                experienced += 1
            if profile.open_to_work:
                open_to_work += 1
            if profile.current_location:
                location_counts[str(profile.current_location)] += 1
            notice_counts[str(profile.notice_period or "UNKNOWN")] += 1
            experience_counts[EmployerDashboardService._experience_bucket(experience)] += 1

            for skill in EmployerDashboardService._extract_skills(profile, resume_details_by_candidate[candidate_id]):
                skill_counts[skill] += 1
            for education in EmployerDashboardService._extract_education(resume_details_by_candidate[candidate_id]):
                education_counts[education] += 1

        return EmployerAnalyticsCandidateAnalytics(
            top_skills=EmployerDashboardService._distribution(skill_counts, limit=10),
            top_locations=EmployerDashboardService._distribution(location_counts, limit=10),
            experience_distribution=EmployerDashboardService._distribution(experience_counts),
            education_distribution=EmployerDashboardService._distribution(education_counts, limit=10),
            freshers=freshers,
            experienced=experienced,
            open_to_work=open_to_work,
            notice_period_distribution=EmployerDashboardService._distribution(notice_counts),
        )

    @staticmethod
    def _build_job_performance(job_analytics: list[EmployerAnalyticsJobDetail]) -> EmployerAnalyticsJobPerformance:
        return EmployerAnalyticsJobPerformance(
            best_performing_jobs=sorted(
                job_analytics,
                key=lambda job: (job.hired, job.conversion_rate, job.applications),
                reverse=True,
            )[:10],
            lowest_performing_jobs=sorted(
                job_analytics,
                key=lambda job: (job.conversion_rate, job.applications),
            )[:10],
            most_viewed_jobs=sorted(job_analytics, key=lambda job: job.views, reverse=True)[:10],
            most_applied_jobs=sorted(job_analytics, key=lambda job: job.applications, reverse=True)[:10],
            highest_conversion_jobs=sorted(job_analytics, key=lambda job: job.conversion_rate, reverse=True)[:10],
            jobs_receiving_no_applications=[
                job for job in job_analytics if job.applications == 0
            ][:10],
        )

    @staticmethod
    def _build_chart_data(
        *,
        application_analytics: EmployerAnalyticsApplicationAnalytics,
        hiring_pipeline: list[EmployerAnalyticsDistributionPoint],
        candidate_analytics: EmployerAnalyticsCandidateAnalytics,
        job_analytics: list[EmployerAnalyticsJobDetail],
    ) -> EmployerAnalyticsCharts:
        trends = application_analytics.application_trends
        status_distribution = application_analytics.application_status_distribution
        return EmployerAnalyticsCharts(
            line_charts={
                "application_trends": EmployerDashboardService._series_chart(
                    "line", [point.label for point in trends], "Applications", [point.applications for point in trends]
                ).model_dump()
            },
            bar_charts={
                "job_applications": EmployerDashboardService._series_chart(
                    "bar", [job.title for job in job_analytics[:10]], "Applications", [job.applications for job in job_analytics[:10]]
                ).model_dump()
            },
            area_charts={
                "daily_applications": EmployerDashboardService._series_chart(
                    "area",
                    [point.label for point in application_analytics.daily_applications],
                    "Applications",
                    [point.applications for point in application_analytics.daily_applications],
                ).model_dump()
            },
            pie_charts={
                "application_status_distribution": EmployerDashboardService._distribution_chart(
                    "pie", status_distribution
                ).model_dump()
            },
            donut_charts={
                "candidate_sources": EmployerDashboardService._distribution_chart(
                    "donut", application_analytics.application_sources
                ).model_dump()
            },
            stacked_charts={
                "hiring_pipeline": EmployerDashboardService._series_chart(
                    "stacked",
                    [point.label for point in hiring_pipeline],
                    "Candidates",
                    [point.count for point in hiring_pipeline],
                ).model_dump()
            },
        )

    @staticmethod
    def _bucket_application_events(events, period: str, date_from: date, date_to: date) -> list[EmployerAnalyticsTrendPoint]:
        counts = Counter(
            EmployerDashboardService._period_key(event["applied_at"].date(), period)
            for event in events
        )
        keys = EmployerDashboardService._period_keys(date_from, date_to, period)
        return [
            EmployerAnalyticsTrendPoint(
                period=key,
                label=key,
                applications=int(counts.get(key, 0)),
            )
            for key in keys
        ]

    @staticmethod
    def _period_key(value: date, period: str) -> str:
        if period == "weekly":
            year, week, _ = value.isocalendar()
            return f"{year}-W{week:02d}"
        if period == "monthly":
            return value.strftime("%Y-%m")
        if period == "yearly":
            return value.strftime("%Y")
        return value.isoformat()

    @staticmethod
    def _period_keys(date_from: date, date_to: date, period: str) -> list[str]:
        keys: list[str] = []
        cursor = date_from
        if period == "yearly":
            return [str(year) for year in range(date_from.year, date_to.year + 1)]
        while cursor <= date_to:
            key = EmployerDashboardService._period_key(cursor, period)
            if not keys or keys[-1] != key:
                keys.append(key)
            if period == "weekly":
                cursor += timedelta(days=7)
            elif period == "monthly":
                cursor = date(cursor.year + (1 if cursor.month == 12 else 0), 1 if cursor.month == 12 else cursor.month + 1, 1)
            else:
                cursor += timedelta(days=1)
        return keys

    @staticmethod
    def _distribution(counter: Counter, limit: Optional[int] = None) -> list[EmployerAnalyticsDistributionPoint]:
        total = sum(int(value or 0) for value in counter.values())
        items = counter.most_common(limit)
        return [
            EmployerAnalyticsDistributionPoint(
                key=str(key),
                label=str(key).replace("_", " ").title(),
                count=int(count or 0),
                percent=round((int(count or 0) / total) * 100, 1) if total else 0,
            )
            for key, count in items
            if key
        ]

    @staticmethod
    def _average_duration_days(pairs: Iterable[tuple[Optional[datetime], Optional[datetime]]]) -> float:
        durations = [
            max(0, (end - start).total_seconds() / 86400)
            for start, end in pairs
            if start and end
        ]
        return round(sum(durations) / len(durations), 1) if durations else 0

    @staticmethod
    def _experience_bucket(experience: float) -> str:
        if experience <= 0:
            return "FRESHER"
        if experience < 2:
            return "0-2"
        if experience < 5:
            return "2-5"
        if experience < 10:
            return "5-10"
        return "10+"

    @staticmethod
    def _extract_skills(profile, resume_details) -> list[str]:
        skills: list[str] = []
        if getattr(profile, "skills_summary", None):
            skills.extend(part.strip() for part in str(profile.skills_summary).replace(";", ",").split(","))
        for detail in resume_details:
            raw = getattr(detail, "skills_json", None)
            if isinstance(raw, dict):
                values = raw.get("skills") or raw.get("technical_skills") or raw.values()
                values = [values] if isinstance(values, str) else values
                for value in values:
                    if isinstance(value, str):
                        skills.append(value.strip())
                    elif isinstance(value, list):
                        skills.extend(str(item).strip() for item in value if item)
        return [skill for skill in skills if skill]

    @staticmethod
    def _extract_education(resume_details) -> list[str]:
        values: list[str] = []
        for detail in resume_details:
            raw = getattr(detail, "education_json", None)
            entries = raw if isinstance(raw, list) else (raw.get("education") if isinstance(raw, dict) else None)
            if isinstance(entries, dict):
                entries = [entries]
            for entry in (entries if isinstance(entries, list) else []):
                if isinstance(entry, dict):
                    degree = entry.get("degree") or entry.get("qualification") or entry.get("course")
                    if degree:
                        values.append(str(degree))
                elif isinstance(entry, str):
                    values.append(entry)
        return values

    @staticmethod
    def _series_chart(chart_type: str, labels: list[str], label: str, values: list[int]) -> EmployerAnalyticsChartSeries:
        return EmployerAnalyticsChartSeries(
            chart_type=chart_type,
            labels=labels,
            datasets=[{"label": label, "data": values}],
        )

    @staticmethod
    def _distribution_chart(chart_type: str, points: list[EmployerAnalyticsDistributionPoint]) -> EmployerAnalyticsChartSeries:
        return EmployerDashboardService._series_chart(
            chart_type,
            [point.label for point in points],
            "Count",
            [point.count for point in points],
        )

    @staticmethod
    def _format_number(value: int | float) -> str:
        return f"{value:,}"

    @staticmethod
    def _average_days(rows) -> int:
        durations = [
            max(0, (milestone_at - applied_at).days)
            for applied_at, milestone_at in rows
            if applied_at and milestone_at
        ]
        if not durations:
            return 0
        return round(sum(durations) / len(durations))

    @staticmethod
    def _build_company_summary(
        employer: EmployerProfile,
        company: Optional[CompanyProfile],
    ) -> EmployerDashboardCompanySummary:
        return EmployerDashboardCompanySummary(
            employer_id=str(employer.id),
            company_id=company.company_id if company else None,
            company_name=company.company_name if company else employer.company_name,
            company_email=employer.company_email,
            company_mobile=employer.company_mobile,
            company_website=company.website if company else employer.company_website,
            company_logo_url=(company.logo_path if company else employer.company_logo_url),
            industry=company.industry if company else employer.industry,
            company_size=company.size if company else employer.company_size,
            company_location=company.location if company else employer.company_location,
            verification_status=employer.verification_status,
            is_verified=bool(employer.is_verified),
        )

    @staticmethod
    def _build_stat_cards(counts: dict[str, int]) -> List[EmployerDashboardStatCard]:
        return [
            EmployerDashboardStatCard(
                key="posted_jobs",
                label="Posted Jobs",
                value=counts["total_jobs"],
            ),
            EmployerDashboardStatCard(
                key="active_jobs",
                label="Active Jobs",
                value=counts["active_jobs"],
            ),
            EmployerDashboardStatCard(
                key="applications",
                label="Applications",
                value=counts["total_applications"],
            ),
            EmployerDashboardStatCard(
                key="pending_applications",
                label="Pending Applications",
                value=counts["pending_applications"],
            ),
            EmployerDashboardStatCard(
                key="shortlisted_candidates",
                label="Shortlisted Candidates",
                value=counts["shortlisted_candidates"],
            ),
            EmployerDashboardStatCard(
                key="scheduled_interviews",
                label="Scheduled Interviews",
                value=counts["scheduled_interviews"],
            ),
            EmployerDashboardStatCard(
                key="unread_messages",
                label="Unread Messages",
                value=counts["unread_messages"],
            ),
            EmployerDashboardStatCard(
                key="profile_views",
                label="Profile Views",
                value=counts["total_views"],
            ),
        ]

    @staticmethod
    def _build_statistics(
        application_status_rows,
        job_status_rows,
        applications_over_time_rows,
    ) -> EmployerDashboardStats:
        application_counts = _counts_by_key(application_status_rows)
        application_counts["INTERVIEW"] = sum(
            application_counts.get(status, 0)
            for status in ("INTERVIEW", "INTERVIEW_SCHEDULED", "INTERVIEWED")
        )
        job_counts = _counts_by_key(job_status_rows)
        return EmployerDashboardStats(
            application_status=[
                EmployerDashboardApplicationStatusCount(
                    status=status,
                    count=application_counts.get(status, 0),
                )
                for status in _APPLICATION_STATUSES
            ],
            job_status=[
                EmployerDashboardJobStatusCount(
                    status=status,
                    count=job_counts.get(status, 0),
                )
                for status in _JOB_STATUSES
            ],
            applications_over_time=[
                EmployerDashboardTimeSeriesPoint(
                    date=_coerce_date(applied_date),
                    applications=int(count or 0),
                )
                for applied_date, count in applications_over_time_rows
            ],
        )

    @staticmethod
    def _build_job_stage_analytics(
        job_stage_rows,
        stage_transition_rows,
    ) -> List[EmployerDashboardJobStageAnalytics]:
        jobs_by_id: dict[str, Job] = {}
        counts_by_job: dict[str, dict[str, int]] = {}
        transitions_by_job: dict[str, list[EmployerDashboardStageTransition]] = {}

        for row in job_stage_rows:
            job, stage, count = row
            job_id = job.job_id
            jobs_by_id[job_id] = job
            counts_by_job.setdefault(job_id, {})[str(stage)] = int(count or 0)

        for row in stage_transition_rows:
            job, from_stage, to_stage, count = row
            job_id = job.job_id
            jobs_by_id[job_id] = job
            transitions_by_job.setdefault(job_id, []).append(
                EmployerDashboardStageTransition(
                    from_status=str(from_stage) if from_stage else None,
                    to_status=str(to_stage),
                    count=int(count or 0),
                )
            )

        analytics: list[EmployerDashboardJobStageAnalytics] = []
        for job_id, job in jobs_by_id.items():
            stage_counts = counts_by_job.get(job_id, {})
            ordered_statuses = _ordered_statuses(stage_counts.keys())
            analytics.append(
                EmployerDashboardJobStageAnalytics(
                    job=_job_summary(job),
                    total_applications=sum(stage_counts.values()),
                    stage_counts=[
                        EmployerDashboardStageCount(
                            status=status,
                            count=stage_counts.get(status, 0),
                        )
                        for status in ordered_statuses
                    ],
                    stage_transitions=transitions_by_job.get(job_id, []),
                )
            )

        return analytics

    @staticmethod
    def _build_application_row(row) -> EmployerDashboardRecentApplication:
        application, job, candidate, user = row
        return EmployerDashboardRecentApplication(
            application_id=application.application_id,
            application_status=application.application_status,
            applied_at=application.applied_at,
            source=application.source,
            job=_job_summary(job),
            candidate=_candidate_summary(candidate, user),
        )

    @staticmethod
    def _build_job_table_row(row) -> EmployerDashboardJobTableRow:
        job, applications_count, shortlisted_count, view_count = row
        return EmployerDashboardJobTableRow(
            job_id=job.job_id,
            title=job.title,
            status=job.status,
            location=job.location,
            employment_type=job.employment_type,
            work_mode=job.work_mode,
            no_of_openings=job.no_of_openings,
            posted_at=job.created_at,
            application_deadline=job.application_deadline,
            applications_count=int(applications_count or 0),
            shortlisted_count=int(shortlisted_count or 0),
            view_count=int(view_count or 0),
        )

    @staticmethod
    def _build_interview_row(row) -> EmployerDashboardInterview:
        interview, application, job, candidate, user = row
        return EmployerDashboardInterview(
            interview_id=interview.interview_id,
            application_id=application.application_id,
            scheduled_at=EmployerDashboardService._interview_scheduled_at(interview),
            mode=interview.mode,
            location_or_link=(
                getattr(interview, "location_or_link", None)
                or getattr(interview, "meeting_link", None)
                or getattr(interview, "interview_location", None)
            ),
            interviewer_name=interview.interviewer_name,
            status=interview.status,
            job=_job_summary(job),
            candidate=_candidate_summary(candidate, user),
        )

    @staticmethod
    def _interview_scheduled_at(interview) -> datetime | None:
        scheduled_at = getattr(interview, "scheduled_at", None)
        if scheduled_at is not None:
            return scheduled_at

        interview_date = getattr(interview, "interview_date", None)
        interview_time = getattr(interview, "interview_time", None)
        if interview_date is None:
            return None
        return datetime.combine(interview_date, interview_time or time.min)

    @staticmethod
    def _build_activity_row(row) -> EmployerDashboardRecentActivity:
        audit, job = unpack_activity_row(row)
        activity = build_recent_activity(
            audit,
            job_title=getattr(job, "title", None),
        )
        return EmployerDashboardRecentActivity(**activity)
