from typing import Dict, List

from pydantic import BaseModel, Field


class MonthlyCountItem(BaseModel):
    month: str
    count: int


class StatusCountItem(BaseModel):
    status: str
    count: int


class UserDistributionResponse(BaseModel):
    total_users: int = 0
    total_candidates: int
    total_employers: int
    total_admins: int


class JobAnalyticsResponse(BaseModel):
    total_jobs: int = 0
    active_jobs: int
    inactive_jobs: int = 0
    closed_jobs: int
    draft_jobs: int
    expired_jobs: int
    status_counts: Dict[str, int] = Field(default_factory=dict)
    jobs_posted_trend: List[MonthlyCountItem] = Field(default_factory=list)
    jobs_closed_trend: List[MonthlyCountItem] = Field(default_factory=list)
    grouping: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    timezone: str | None = None


class ApplicationAnalyticsResponse(BaseModel):
    total_applications: int = 0
    applications_trend: List[MonthlyCountItem] = Field(default_factory=list)
    application_funnel: List[StatusCountItem] = Field(default_factory=list)
    grouping: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    timezone: str | None = None


class CompanyAnalyticsResponse(BaseModel):
    approved_companies: int = 0
    pending_companies: int = 0
    rejected_companies: int = 0


class SubscriptionAnalyticsResponse(BaseModel):
    candidate_subscriptions: int = 0
    admin_subscriptions: int = 0
    active_candidate_plans: int = 0
    expired_candidate_plans: int = 0
    active_admin_plans: int = 0
    expired_admin_plans: int = 0


class DashboardAnalyticsResponse(
    UserDistributionResponse,
    JobAnalyticsResponse,
    ApplicationAnalyticsResponse,
    CompanyAnalyticsResponse,
    SubscriptionAnalyticsResponse,
):
    total_companies: int
    total_active_jobs: int
    total_inactive_jobs: int = 0
    total_closed_jobs: int
    total_draft_jobs: int
    total_subscriptions: int
    monthly_registrations: List[MonthlyCountItem]
    monthly_jobs_posted: List[MonthlyCountItem]
    monthly_jobs_closed: List[MonthlyCountItem] = Field(default_factory=list)
    registration_trend: List[MonthlyCountItem] = Field(default_factory=list)
    job_status_counts: Dict[str, int]
    range: dict[str, str] | None = None
    current_totals: dict[str, int] | None = None
    period_metrics: dict[str, int] | None = None
    grouping: str | None = None


class RegistrationTrendsResponse(BaseModel):
    monthly_registrations: List[MonthlyCountItem]
    registration_trend: List[MonthlyCountItem] = Field(default_factory=list)
    grouping: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    timezone: str | None = None
