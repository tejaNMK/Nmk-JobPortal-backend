from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.employer_dashboard_schema import EmployerDashboardFilters
from app.model.authentication.users import Users
from app.model.candidate_model.application_status_history import ApplicationStatusHistory
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.message import Message
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.interview import Interview
from app.model.employer_model.job import Job
from app.model.employer_model.job_metrics import JobMetrics
from app.model.employer_model.job_posting_audit import JobPostingAudit


def _application_filters(
    employer_id: str,
    filters: EmployerDashboardFilters,
    *,
    include_status: bool = True,
):
    conditions = [
        Job.employer_id == employer_id,
        Job.is_deleted.is_(False),
        JobApplication.is_deleted.is_(False),
    ]
    if filters.job_id:
        conditions.append(Job.job_id == filters.job_id)
    if getattr(filters, "department", None):
        conditions.append(Job.team == filters.department)
    if getattr(filters, "employment_type", None):
        conditions.append(Job.employment_type == filters.employment_type)
    if getattr(filters, "location", None):
        conditions.append(Job.location == filters.location)
    if getattr(filters, "hiring_manager", None):
        conditions.append(Job.created_by == filters.hiring_manager)
    if getattr(filters, "status", None):
        conditions.append(Job.status == filters.status)
    if include_status and filters.application_status:
        conditions.append(JobApplication.application_status == filters.application_status)
    if filters.date_from:
        conditions.append(JobApplication.applied_at >= datetime.combine(filters.date_from, time.min))
    if filters.date_to:
        conditions.append(JobApplication.applied_at <= datetime.combine(filters.date_to, time.max))
    return and_(*conditions)


def _job_filters(employer_id: str, filters: EmployerDashboardFilters):
    conditions = [
        Job.employer_id == employer_id,
        Job.is_deleted.is_(False),
    ]
    if filters.job_id:
        conditions.append(Job.job_id == filters.job_id)
    if getattr(filters, "department", None):
        conditions.append(Job.team == filters.department)
    if getattr(filters, "employment_type", None):
        conditions.append(Job.employment_type == filters.employment_type)
    if getattr(filters, "location", None):
        conditions.append(Job.location == filters.location)
    if getattr(filters, "hiring_manager", None):
        conditions.append(Job.created_by == filters.hiring_manager)
    if getattr(filters, "status", None):
        conditions.append(Job.status == filters.status)
    return and_(*conditions)


def _count_if(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _count_distinct_if(condition, value):
    return func.count(func.distinct(case((condition, value), else_=None)))


class EmployerDashboardRepo:
    @staticmethod
    async def fetch_employer_profile(
        session: AsyncSession,
        user_id: UUID,
    ) -> Optional[EmployerProfile]:
        result = await session.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == user_id,
                EmployerProfile.is_deleted == 0,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def fetch_company_profile(
        session: AsyncSession,
        employer_id: str,
    ) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.employer_id == employer_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def fetch_job_filter_options(
        session: AsyncSession,
        employer_id: str,
    ) -> List[Job]:
        result = await session.execute(
            select(Job)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                Job.status == "PUBLISHED",
            )
            .order_by(Job.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def fetch_stat_counts(
        session: AsyncSession,
        employer_id: str,
        receiver_user_id: UUID,
    ) -> Dict[str, int]:
        total_jobs = await session.scalar(
            select(func.count(Job.job_id)).where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
            )
        )
        active_jobs = await session.scalar(
            select(func.count(Job.job_id)).where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                Job.status == "PUBLISHED",
            )
        )
        total_applications = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )
        pending_applications = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                JobApplication.application_status.in_(("APPLIED", "REVIEW")),
            )
        )
        shortlisted = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                JobApplication.application_status == "SHORTLISTED",
            )
        )
        interviews = await session.scalar(
            select(func.count(Interview.interview_id))
            .join(JobApplication, JobApplication.application_id == Interview.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                Interview.status == "SCHEDULED",
            )
        )
        unread_messages = await session.scalar(
            select(func.count(Message.message_id)).where(
                Message.receiver_id == receiver_user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
        )
        total_views = await session.scalar(
            select(func.coalesce(func.sum(JobMetrics.view_count), 0))
            .join(Job, Job.job_id == JobMetrics.job_id)
            .where(Job.employer_id == employer_id, Job.is_deleted.is_(False))
        )

        return {
            "total_jobs": int(total_jobs or 0),
            "active_jobs": int(active_jobs or 0),
            "total_applications": int(total_applications or 0),
            "pending_applications": int(pending_applications or 0),
            "shortlisted_candidates": int(shortlisted or 0),
            "scheduled_interviews": int(interviews or 0),
            "unread_messages": int(unread_messages or 0),
            "total_views": int(total_views or 0),
        }

    @staticmethod
    async def fetch_application_status_counts(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> List[Tuple[str, int]]:
        rows = await session.execute(
            select(
                JobApplication.application_status,
                func.count(JobApplication.application_id).label("cnt"),
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(_application_filters(employer_id, filters))
            .group_by(JobApplication.application_status)
        )
        return [(row.application_status, row.cnt) for row in rows.all()]

    @staticmethod
    async def fetch_job_stage_counts(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        rows = await session.execute(
            select(
                Job,
                JobApplication.application_status.label("stage"),
                func.count(JobApplication.application_id).label("cnt"),
            )
            .join(JobApplication, JobApplication.job_id == Job.job_id)
            .where(_application_filters(employer_id, filters, include_status=False))
            .group_by(Job.job_id, JobApplication.application_status)
            .order_by(Job.created_at.desc(), JobApplication.application_status.asc())
        )
        return rows.all()

    @staticmethod
    async def fetch_job_stage_transition_counts(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        conditions = [
            Job.employer_id == employer_id,
            Job.is_deleted.is_(False),
            JobApplication.is_deleted.is_(False),
            ApplicationStatusHistory.new_status.isnot(None),
        ]
        if filters.job_id:
            conditions.append(Job.job_id == filters.job_id)
        if filters.date_from:
            conditions.append(
                ApplicationStatusHistory.changed_at >= datetime.combine(filters.date_from, time.min)
            )
        if filters.date_to:
            conditions.append(
                ApplicationStatusHistory.changed_at <= datetime.combine(filters.date_to, time.max)
            )

        rows = await session.execute(
            select(
                Job,
                ApplicationStatusHistory.old_status.label("from_stage"),
                ApplicationStatusHistory.new_status.label("to_stage"),
                func.count(ApplicationStatusHistory.history_id).label("cnt"),
            )
            .join(JobApplication, JobApplication.job_id == Job.job_id)
            .join(
                ApplicationStatusHistory,
                ApplicationStatusHistory.application_id == JobApplication.application_id,
            )
            .where(and_(*conditions))
            .group_by(
                Job.job_id,
                ApplicationStatusHistory.old_status,
                ApplicationStatusHistory.new_status,
            )
            .order_by(
                Job.created_at.desc(),
                ApplicationStatusHistory.old_status.asc().nulls_first(),
                ApplicationStatusHistory.new_status.asc(),
            )
        )
        return rows.all()

    @staticmethod
    async def fetch_job_status_counts(
        session: AsyncSession,
        employer_id: str,
    ) -> List[Tuple[str, int]]:
        rows = await session.execute(
            select(Job.status, func.count(Job.job_id).label("cnt"))
            .where(Job.employer_id == employer_id, Job.is_deleted.is_(False))
            .group_by(Job.status)
        )
        return [(row.status, row.cnt) for row in rows.all()]

    @staticmethod
    async def fetch_applications_over_time(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> List[Tuple[date, int]]:
        applied_date = func.date(JobApplication.applied_at).label("applied_date")
        rows = await session.execute(
            select(applied_date, func.count(JobApplication.application_id).label("cnt"))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(_application_filters(employer_id, filters))
            .group_by(applied_date)
            .order_by(applied_date.asc())
        )
        return [(row.applied_date, row.cnt) for row in rows.all()]

    @staticmethod
    async def fetch_recent_applications(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(JobApplication, Job, CandidateProfile, Users)
            .join(Job, Job.job_id == JobApplication.job_id)
            .join(CandidateProfile, CandidateProfile.candidate_id == JobApplication.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(_application_filters(employer_id, filters))
            .order_by(JobApplication.applied_at.desc())
            .limit(filters.limit)
        )
        return result.all()

    @staticmethod
    async def fetch_active_jobs(
        session: AsyncSession,
        employer_id: str,
        limit: int,
    ):
        applications_count = func.count(func.distinct(JobApplication.application_id)).label("applications_count")
        shortlist_count = _count_distinct_if(
            JobApplication.application_status == "SHORTLISTED",
            JobApplication.application_id,
        ).label("shortlisted_count")
        view_count = func.coalesce(func.max(JobMetrics.view_count), 0).label("view_count")
        result = await session.execute(
            select(Job, applications_count, shortlist_count, view_count)
            .outerjoin(
                JobApplication,
                and_(
                    JobApplication.job_id == Job.job_id,
                    JobApplication.is_deleted.is_(False),
                ),
            )
            .outerjoin(JobMetrics, JobMetrics.job_id == Job.job_id)
            .where(Job.employer_id == employer_id, Job.is_deleted.is_(False))
            .group_by(Job.job_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return result.all()

    @staticmethod
    async def fetch_upcoming_interviews(
        session: AsyncSession,
        employer_id: str,
        limit: int,
    ):
        result = await session.execute(
            select(Interview, JobApplication, Job, CandidateProfile, Users)
            .join(JobApplication, JobApplication.application_id == Interview.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .join(CandidateProfile, CandidateProfile.candidate_id == JobApplication.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                Interview.status == "SCHEDULED",
            )
            .order_by(
                Interview.interview_date.asc(),
                Interview.interview_time.asc(),
            )
            .limit(limit)
        )
        return result.all()

    @staticmethod
    async def fetch_recent_activity(
        session: AsyncSession,
        employer_id: str,
        limit: int,
    ):
        result = await session.execute(
            select(JobPostingAudit, Job)
            .outerjoin(Job, Job.job_id == JobPostingAudit.job_id)
            .where(JobPostingAudit.employer_id == employer_id)
            .order_by(JobPostingAudit.created_at.desc())
            .limit(limit)
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_top_jobs(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
        limit: int = 10,
    ):
        applications_count = func.count(func.distinct(JobApplication.application_id)).label("applications_count")
        shortlisted_count = func.count(
            func.distinct(
                case(
                    (
                        JobApplication.application_status == "SHORTLISTED",
                        JobApplication.application_id,
                    ),
                    else_=None,
                )
            )
        ).label("shortlisted_count")
        view_count = func.coalesce(func.max(JobMetrics.view_count), 0).label("view_count")

        result = await session.execute(
            select(Job, applications_count, shortlisted_count, view_count)
            .outerjoin(
                JobApplication,
                and_(
                    JobApplication.job_id == Job.job_id,
                    JobApplication.is_deleted.is_(False),
                    *(
                        [JobApplication.applied_at >= datetime.combine(filters.date_from, time.min)]
                        if filters.date_from
                        else []
                    ),
                    *(
                        [JobApplication.applied_at <= datetime.combine(filters.date_to, time.max)]
                        if filters.date_to
                        else []
                    ),
                ),
            )
            .outerjoin(JobMetrics, JobMetrics.job_id == Job.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                *([Job.job_id == filters.job_id] if filters.job_id else []),
            )
            .group_by(Job.job_id)
            .order_by(applications_count.desc(), Job.created_at.desc())
            .limit(limit)
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_candidate_sources(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> List[Tuple[str, int]]:
        rows = await session.execute(
            select(
                JobApplication.source,
                func.count(JobApplication.application_id).label("cnt"),
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                _application_filters(employer_id, filters, include_status=False),
                JobApplication.source.isnot(None),
                JobApplication.source != "",
            )
            .group_by(JobApplication.source)
            .order_by(func.count(JobApplication.application_id).desc())
        )
        return [(row.source, row.cnt) for row in rows.all()]

    @staticmethod
    async def fetch_analytics_stage_events(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> List[Tuple[str, str]]:
        conditions = [
            Job.employer_id == employer_id,
            Job.is_deleted.is_(False),
            JobApplication.is_deleted.is_(False),
        ]
        if filters.job_id:
            conditions.append(Job.job_id == filters.job_id)
        if filters.date_from:
            conditions.append(JobApplication.applied_at >= datetime.combine(filters.date_from, time.min))
        if filters.date_to:
            conditions.append(JobApplication.applied_at <= datetime.combine(filters.date_to, time.max))

        current_rows = await session.execute(
            select(
                JobApplication.application_id,
                JobApplication.application_status.label("stage"),
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(and_(*conditions))
        )

        history_rows = await session.execute(
            select(
                JobApplication.application_id,
                ApplicationStatusHistory.new_status.label("stage"),
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .join(
                ApplicationStatusHistory,
                ApplicationStatusHistory.application_id == JobApplication.application_id,
            )
            .where(
                and_(*conditions),
                ApplicationStatusHistory.new_status.isnot(None),
            )
        )
        return [
            (row.application_id, row.stage)
            for row in [*current_rows.all(), *history_rows.all()]
            if row.stage
        ]

    @staticmethod
    async def fetch_analytics_stat_counts(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> Dict[str, int]:
        job_conditions = [
            Job.employer_id == employer_id,
            Job.is_deleted.is_(False),
        ]
        if filters.job_id:
            job_conditions.append(Job.job_id == filters.job_id)

        active_jobs = await session.scalar(
            select(func.count(Job.job_id)).where(
                *job_conditions,
                Job.status == "PUBLISHED",
            )
        )
        applications = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(_application_filters(employer_id, filters, include_status=False))
        )
        shortlisted = await session.scalar(
            select(func.count(func.distinct(JobApplication.application_id)))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                _application_filters(employer_id, filters, include_status=False),
                JobApplication.application_status == "SHORTLISTED",
            )
        )
        interviews = await session.scalar(
            select(func.count(Interview.interview_id))
            .join(JobApplication, JobApplication.application_id == Interview.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                _application_filters(employer_id, filters, include_status=False),
                Interview.status.in_(("SCHEDULED", "COMPLETED")),
            )
        )
        profile_views = await session.scalar(
            select(func.coalesce(func.sum(JobMetrics.view_count), 0))
            .join(Job, Job.job_id == JobMetrics.job_id)
            .where(*job_conditions)
        )

        return {
            "active_jobs": int(active_jobs or 0),
            "applications": int(applications or 0),
            "shortlisted": int(shortlisted or 0),
            "interviews": int(interviews or 0),
            "profile_views": int(profile_views or 0),
        }

    @staticmethod
    async def fetch_analytics_overview_counts(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> Dict[str, int]:
        today_start = datetime.combine(date.today(), time.min)
        week_start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), time.min)
        month_start = datetime.combine(date.today().replace(day=1), time.min)

        jobs_row = (
            await session.execute(
                select(
                    func.count(Job.job_id).label("total_jobs"),
                    _count_if(Job.status == "PUBLISHED").label("active_jobs"),
                    _count_if(Job.status == "CLOSED").label("closed_jobs"),
                    _count_if(Job.status == "DRAFT").label("draft_jobs"),
                    _count_if(Job.status == "EXPIRED").label("expired_jobs"),
                    _count_if(Job.status == "PAUSED").label("paused_jobs"),
                ).where(_job_filters(employer_id, filters))
            )
        ).one()

        app_row = (
            await session.execute(
                select(
                    func.count(JobApplication.application_id).label("applications_received"),
                    _count_if(JobApplication.applied_at >= today_start).label("applications_today"),
                    _count_if(JobApplication.applied_at >= week_start).label("applications_this_week"),
                    _count_if(JobApplication.applied_at >= month_start).label("applications_this_month"),
                    _count_if(JobApplication.application_status == "SHORTLISTED").label("candidates_shortlisted"),
                    _count_if(JobApplication.application_status == "REJECTED").label("candidates_rejected"),
                    _count_if(JobApplication.application_status == "HIRED").label("candidates_hired"),
                    _count_if(JobApplication.application_status.in_(("OFFER", "OFFERED", "HIRED"))).label("offers_released"),
                    _count_if(JobApplication.application_status.in_(("ACCEPTED", "HIRED"))).label("offers_accepted"),
                )
                .join(Job, Job.job_id == JobApplication.job_id)
                .where(_application_filters(employer_id, filters, include_status=False))
            )
        ).one()

        interview_row = (
            await session.execute(
                select(
                    _count_if(Interview.status == "SCHEDULED").label("interviews_scheduled"),
                    _count_if(Interview.status == "COMPLETED").label("interviews_completed"),
                )
                .join(JobApplication, JobApplication.application_id == Interview.application_id)
                .join(Job, Job.job_id == JobApplication.job_id)
                .where(_application_filters(employer_id, filters, include_status=False))
            )
        ).one()

        merged = {**jobs_row._mapping, **app_row._mapping, **interview_row._mapping}
        return {key: int(value or 0) for key, value in merged.items()}

    @staticmethod
    async def fetch_analytics_job_rows(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(
                Job,
                func.coalesce(func.max(JobMetrics.view_count), 0).label("views"),
                func.count(func.distinct(JobApplication.application_id)).label("applications"),
                func.count(func.distinct(Interview.interview_id)).label("interviewed"),
                _count_distinct_if(
                    JobApplication.application_status == "SHORTLISTED",
                    JobApplication.application_id,
                ).label("shortlisted"),
                _count_distinct_if(
                    JobApplication.application_status == "REJECTED",
                    JobApplication.application_id,
                ).label("rejected"),
                _count_distinct_if(
                    JobApplication.application_status.in_(("OFFER", "OFFERED", "HIRED")),
                    JobApplication.application_id,
                ).label("offers"),
                _count_distinct_if(
                    JobApplication.application_status == "HIRED",
                    JobApplication.application_id,
                ).label("hired"),
            )
            .outerjoin(
                JobApplication,
                and_(
                    JobApplication.job_id == Job.job_id,
                    JobApplication.is_deleted.is_(False),
                    *(
                        [JobApplication.applied_at >= datetime.combine(filters.date_from, time.min)]
                        if filters.date_from
                        else []
                    ),
                    *(
                        [JobApplication.applied_at <= datetime.combine(filters.date_to, time.max)]
                        if filters.date_to
                        else []
                    ),
                ),
            )
            .outerjoin(Interview, Interview.application_id == JobApplication.application_id)
            .outerjoin(JobMetrics, JobMetrics.job_id == Job.job_id)
            .where(_job_filters(employer_id, filters))
            .group_by(Job.job_id)
            .order_by(Job.created_at.desc())
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_application_events(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(
                JobApplication.application_id,
                JobApplication.applied_at,
                JobApplication.source,
                JobApplication.application_status,
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(_application_filters(employer_id, filters, include_status=False))
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_interview_events(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(Interview)
            .join(JobApplication, JobApplication.application_id == Interview.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(_application_filters(employer_id, filters, include_status=False))
        )
        return list(result.scalars().all())

    @staticmethod
    async def fetch_analytics_candidate_rows(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(CandidateProfile, CandidateResumeDetail)
            .join(JobApplication, JobApplication.candidate_id == CandidateProfile.candidate_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(_application_filters(employer_id, filters, include_status=False))
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_application_milestones(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ):
        result = await session.execute(
            select(
                JobApplication.application_id,
                JobApplication.job_id,
                JobApplication.applied_at,
                ApplicationStatusHistory.new_status,
                ApplicationStatusHistory.changed_at,
            )
            .join(Job, Job.job_id == JobApplication.job_id)
            .outerjoin(
                ApplicationStatusHistory,
                ApplicationStatusHistory.application_id == JobApplication.application_id,
            )
            .where(_application_filters(employer_id, filters, include_status=False))
        )
        return result.all()

    @staticmethod
    async def fetch_analytics_hire_milestones(
        session: AsyncSession,
        employer_id: str,
        filters: EmployerDashboardFilters,
    ) -> List[Tuple[datetime, datetime]]:
        milestone_at = func.min(ApplicationStatusHistory.changed_at).label("milestone_at")
        rows = await session.execute(
            select(JobApplication.applied_at, milestone_at)
            .join(Job, Job.job_id == JobApplication.job_id)
            .join(
                ApplicationStatusHistory,
                ApplicationStatusHistory.application_id == JobApplication.application_id,
            )
            .where(
                _application_filters(employer_id, filters, include_status=False),
                ApplicationStatusHistory.new_status.in_(("HIRED", "OFFERED", "OFFER")),
            )
            .group_by(JobApplication.application_id, JobApplication.applied_at)
        )
        return [
            (row.applied_at, row.milestone_at)
            for row in rows.all()
            if row.applied_at and row.milestone_at
        ]
