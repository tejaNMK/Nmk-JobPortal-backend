from pydantic import BaseModel


class DashboardPeriodMetrics(BaseModel):
    new_users: int = 0
    new_candidates: int = 0
    new_employers: int = 0
    jobs_posted: int = 0
    company_approval_submissions: int = 0
    subscriptions_created: int = 0
    activity_logs: int = 0


class DashboardSummaryResponse(BaseModel):
    total_users: int = 0
    total_candidates: int
    total_employers: int
    total_admins: int
    total_jobs: int
    active_jobs: int
    inactive_jobs: int = 0
    draft_jobs: int
    closed_jobs: int
    total_companies: int
    candidate_subscriptions: int = 0
    admin_subscriptions: int = 0
    range: dict[str, str] | None = None
    current_totals: dict[str, int] | None = None
    period_metrics: DashboardPeriodMetrics | None = None
