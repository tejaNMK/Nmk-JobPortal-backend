from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmployerDashboardFilters(BaseModel):
    job_id: Optional[str] = None
    application_status: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    department: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    hiring_manager: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=25)


class EmployerAnalyticsFilters(BaseModel):
    job_id: Optional[str] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    period: str = "daily"
    department: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    hiring_manager: Optional[str] = None
    status: Optional[str] = None


class EmployerDashboardCompanySummary(BaseModel):
    employer_id: str
    company_id: Optional[str] = None
    company_name: str
    company_email: Optional[str] = None
    company_mobile: Optional[str] = None
    company_website: Optional[str] = None
    company_logo_url: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    company_location: Optional[str] = None
    verification_status: str
    is_verified: bool = False
    model_config = ConfigDict(from_attributes=True)


class EmployerDashboardStatCard(BaseModel):
    key: str
    label: str
    value: int
    helper_text: Optional[str] = None
    formatted_value: Optional[str] = None


class EmployerAnalyticsJobOption(BaseModel):
    job_id: str
    title: str


class EmployerAnalyticsFilterOptions(BaseModel):
    jobs: List[EmployerAnalyticsJobOption]


class EmployerDashboardApplicationStatusCount(BaseModel):
    status: str
    count: int


class EmployerDashboardJobStatusCount(BaseModel):
    status: str
    count: int


class EmployerDashboardStageCount(BaseModel):
    status: str
    count: int


class EmployerDashboardStageTransition(BaseModel):
    from_status: Optional[str] = None
    to_status: str
    count: int


class EmployerDashboardTimeSeriesPoint(BaseModel):
    date: date
    applications: int


class EmployerAnalyticsFunnelStage(BaseModel):
    stage: str
    label: str
    count: int


class EmployerAnalyticsCandidateSource(BaseModel):
    source: str
    label: str
    percent: int


class EmployerAnalyticsTopJob(BaseModel):
    job_id: str
    title: str
    status: str
    applications: int = 0
    views: int = 0
    conversion_rate: float = 0


class EmployerAnalyticsMetric(BaseModel):
    key: str
    label: str
    value: int = 0
    formatted_value: str = "0"


class EmployerAnalyticsDistributionPoint(BaseModel):
    key: str
    label: str
    count: int = 0
    percent: float = 0


class EmployerAnalyticsTrendPoint(BaseModel):
    period: str
    label: str
    applications: int = 0


class EmployerAnalyticsChartSeries(BaseModel):
    chart_type: str
    labels: List[str]
    datasets: List[dict]


class EmployerAnalyticsOverview(BaseModel):
    total_jobs: int = 0
    active_jobs: int = 0
    closed_jobs: int = 0
    draft_jobs: int = 0
    expired_jobs: int = 0
    paused_jobs: int = 0
    applications_received: int = 0
    applications_today: int = 0
    applications_this_week: int = 0
    applications_this_month: int = 0
    candidates_shortlisted: int = 0
    candidates_rejected: int = 0
    candidates_hired: int = 0
    interviews_scheduled: int = 0
    interviews_completed: int = 0
    offers_released: int = 0
    offers_accepted: int = 0


class EmployerAnalyticsJobDetail(BaseModel):
    job_id: str
    title: str
    status: str
    posted_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    views: int = 0
    unique_views: int = 0
    applications: int = 0
    shortlisted: int = 0
    rejected: int = 0
    interviewed: int = 0
    offers: int = 0
    hired: int = 0
    conversion_rate: float = 0
    average_time_to_hire: float = 0
    average_time_to_shortlist: float = 0
    average_response_time: float = 0


class EmployerAnalyticsApplicationAnalytics(BaseModel):
    daily_applications: List[EmployerAnalyticsTrendPoint]
    weekly_applications: List[EmployerAnalyticsTrendPoint]
    monthly_applications: List[EmployerAnalyticsTrendPoint]
    yearly_applications: List[EmployerAnalyticsTrendPoint]
    application_sources: List[EmployerAnalyticsDistributionPoint]
    application_trends: List[EmployerAnalyticsTrendPoint]
    application_status_distribution: List[EmployerAnalyticsDistributionPoint]


class EmployerAnalyticsInterviewAnalytics(BaseModel):
    scheduled: int = 0
    completed: int = 0
    cancelled: int = 0
    rescheduled: int = 0
    upcoming: int = 0
    todays_interviews: int = 0
    success_rate: float = 0
    average_interview_duration: float = 0


class EmployerAnalyticsCandidateAnalytics(BaseModel):
    top_skills: List[EmployerAnalyticsDistributionPoint]
    top_locations: List[EmployerAnalyticsDistributionPoint]
    experience_distribution: List[EmployerAnalyticsDistributionPoint]
    education_distribution: List[EmployerAnalyticsDistributionPoint]
    freshers: int = 0
    experienced: int = 0
    open_to_work: int = 0
    notice_period_distribution: List[EmployerAnalyticsDistributionPoint]


class EmployerAnalyticsJobPerformance(BaseModel):
    best_performing_jobs: List[EmployerAnalyticsJobDetail]
    lowest_performing_jobs: List[EmployerAnalyticsJobDetail]
    most_viewed_jobs: List[EmployerAnalyticsJobDetail]
    most_applied_jobs: List[EmployerAnalyticsJobDetail]
    highest_conversion_jobs: List[EmployerAnalyticsJobDetail]
    jobs_receiving_no_applications: List[EmployerAnalyticsJobDetail]


class EmployerAnalyticsCharts(BaseModel):
    line_charts: dict
    bar_charts: dict
    area_charts: dict
    pie_charts: dict
    donut_charts: dict
    stacked_charts: dict


class EmployerDashboardStats(BaseModel):
    application_status: List[EmployerDashboardApplicationStatusCount]
    job_status: List[EmployerDashboardJobStatusCount]
    applications_over_time: List[EmployerDashboardTimeSeriesPoint]


class EmployerDashboardCandidateSummary(BaseModel):
    candidate_id: str
    user_id: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    headline: Optional[str] = None
    current_location: Optional[str] = None
    total_experience: Optional[float] = None
    profile_image_url: Optional[str] = None


class EmployerDashboardJobSummary(BaseModel):
    job_id: str
    title: str
    status: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    posted_at: Optional[datetime] = None
    application_deadline: Optional[datetime] = None


class EmployerDashboardRecentApplication(BaseModel):
    application_id: str
    application_status: str
    applied_at: datetime
    source: Optional[str] = None
    job: EmployerDashboardJobSummary
    candidate: EmployerDashboardCandidateSummary


class EmployerDashboardJobTableRow(BaseModel):
    job_id: str
    title: str
    status: str
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_mode: Optional[str] = None
    no_of_openings: int
    posted_at: datetime
    application_deadline: Optional[datetime] = None
    applications_count: int = 0
    shortlisted_count: int = 0
    view_count: int = 0


class EmployerDashboardJobStageAnalytics(BaseModel):
    job: EmployerDashboardJobSummary
    total_applications: int = 0
    stage_counts: List[EmployerDashboardStageCount]
    stage_transitions: List[EmployerDashboardStageTransition]


class EmployerDashboardInterview(BaseModel):
    interview_id: str
    application_id: str
    scheduled_at: Optional[datetime] = None
    mode: Optional[str] = None
    location_or_link: Optional[str] = None
    interviewer_name: Optional[str] = None
    status: Optional[str] = None
    job: EmployerDashboardJobSummary
    candidate: EmployerDashboardCandidateSummary


class EmployerDashboardRecentActivity(BaseModel):
    id: str
    activity_id: str
    activity_type: str
    message: str
    title: Optional[str] = None
    status: Optional[str] = None
    created_at: datetime
    description: Optional[str] = None
    happened_at: datetime
    job_id: Optional[str] = None


class EmployerDashboardFilterOptions(BaseModel):
    statuses: List[str]
    jobs: List[EmployerDashboardJobSummary]


class EmployerDashboardPackageSummary(BaseModel):
    package_name: Optional[str] = None
    posted_jobs_used: int = 0
    posted_jobs_limit: int = 0
    featured_jobs_used: int = 0
    featured_jobs_limit: int = 0
    expires_on: Optional[datetime] = None


class EmployerDashboardResponse(BaseModel):
    company_summary: EmployerDashboardCompanySummary
    filters: EmployerDashboardFilters
    filter_options: EmployerDashboardFilterOptions
    stat_cards: List[EmployerDashboardStatCard]
    statistics: EmployerDashboardStats
    recent_applications: List[EmployerDashboardRecentApplication]
    active_jobs: List[EmployerDashboardJobTableRow]
    job_stage_analytics: List[EmployerDashboardJobStageAnalytics]
    upcoming_interviews: List[EmployerDashboardInterview]
    recent_activity: List[EmployerDashboardRecentActivity]
    package_summary: Optional[EmployerDashboardPackageSummary] = None
    model_config = ConfigDict(from_attributes=True)


class EmployerAnalyticsResponse(BaseModel):
    filter_options: EmployerAnalyticsFilterOptions
    stat_cards: List[EmployerDashboardStatCard]
    applications_over_time: List[EmployerDashboardTimeSeriesPoint]
    hiring_funnel: List[EmployerAnalyticsFunnelStage]
    candidate_source: List[EmployerAnalyticsCandidateSource]
    top_jobs: List[EmployerAnalyticsTopJob]
    overview_metrics: Optional[EmployerAnalyticsOverview] = None
    job_analytics: List[EmployerAnalyticsJobDetail] = Field(default_factory=list)
    application_analytics: Optional[EmployerAnalyticsApplicationAnalytics] = None
    hiring_pipeline: List[EmployerAnalyticsDistributionPoint] = Field(default_factory=list)
    interview_analytics: Optional[EmployerAnalyticsInterviewAnalytics] = None
    candidate_analytics: Optional[EmployerAnalyticsCandidateAnalytics] = None
    job_performance: Optional[EmployerAnalyticsJobPerformance] = None
    chart_data: Optional[EmployerAnalyticsCharts] = None
    model_config = ConfigDict(from_attributes=True)
