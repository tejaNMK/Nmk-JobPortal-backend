from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


# ── 1. Stat Bar ───────────────────────────────────────────────────────────────
class DashboardStatBar(BaseModel):
    profile_views: int = 0
    followings: int = 0
    cv_list: int = 0
    messages: int = 0
    model_config = ConfigDict(from_attributes=True)


# ── 2 & 3. Profile Summary (sidebar + profile card) ──────────────────────────
class DashboardProfileSummary(BaseModel):
   
    user_id: UUID
    first_name: str
    last_name: Optional[str] = None
    name: str                                   # pre-joined "first last" for convenience
    email: Optional[str] = None                # shown as identity subtitle in sidebar
    phone: Optional[str] = None                # shown on profile card with phone icon
    avatar: Optional[str] = None               # circular avatar on profile card
    cover: Optional[str] = None                # banner/cover image on profile card
    location: Optional[str] = None             # shown under name on profile card
    open_to_work: bool                         # drives the sidebar toggle
    open_to_work_label: str = "Visible to recruiters"   # UI subtitle under the toggle
    profile_visibility: str                    # "PUBLIC" / "PRIVATE"
    headline: Optional[str] = None             # professional headline on profile card
    profile_completion_pct: int = 0            # profile completion percentage bar
    has_active_resume: bool = False            # whether candidate has an uploaded CV

    model_config = ConfigDict(from_attributes=True)


# ── 4a. Job Card (shared by Applied Jobs and Recommended Jobs) ────────────────
class DashboardJobCard(BaseModel):
    
    job_id: str
    title: str
    location: Optional[str] = None
    work_mode: Optional[str] = None
    badge: Optional[str] = None                 # badge label: "Full Time" / "Contract" etc.
    salary: Optional[str] = None                # pre-formatted salary range string, e.g. "USD5000 - USD6000/Monthly"
    salary_min: Optional[float] = None          # raw lower bound (kept alongside pre-formatted `salary`)
    salary_max: Optional[float] = None          # raw upper bound (kept alongside pre-formatted `salary`)
    salary_currency: str = "USD"                # raw currency code
    salary_period: str = "Monthly"              # raw pay period
    date: Optional[datetime] = None             # job posting date (used in Recommended Jobs)
    company: Optional[str] = None
    logo: Optional[str] = None                  # logo shown bottom-right of card
    industry: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── 4b. Applied Job entry ─────────────────────────────────────────────────────
class DashboardAppliedJob(BaseModel):
    
    application_id: str
    application_status: str                     # e.g. "APPLIED", "INTERVIEW", "OFFER"
    applied: datetime                         
    job: DashboardJobCard

    model_config = ConfigDict(from_attributes=True)


# ── 4c. Application statistics (totals + breakdown) ───────────────────────────
class ApplicationStatusCount(BaseModel):
    status: str
    count: int


class DashboardApplicationStats(BaseModel):
    total: int
    breakdown: List[ApplicationStatusCount]
    model_config = ConfigDict(from_attributes=True)


# ── 5. Active Package Details ─────────────────────────────────────────────────
class DashboardActivePackage(BaseModel):
    
    package_name: str
    price: Optional[str] = None                # free-text, e.g. "USD 10"
    applications: str = "0 / 0"                # pre-formatted "02 / 20" string
    applications_used: int = 0                 # raw used count (kept alongside pre-formatted `applications`)
    applications_limit: int = 0                # raw limit count (kept alongside pre-formatted `applications`)
    started: Optional[datetime] = None         # "STARTED ON" column
    expires: Optional[datetime] = None         # "EXPIRES ON" column (highlighted when near)

    model_config = ConfigDict(from_attributes=True)


# ── 6. Recommended Jobs ───────────────────────────────────────────────────────
class DashboardRecommendedJob(BaseModel):
   
    recommendation_id: str
    match_score: Optional[Decimal] = None
    generated_at: datetime
    job: DashboardJobCard

    model_config = ConfigDict(from_attributes=True)


# ── 7. Followed Company ───────────────────────────────────────────────────────
class DashboardFollowedCompany(BaseModel):
    
    company_id: str
    name: str                                   # was company_name
    industry: Optional[str] = None             # e.g. "Information Technology"
    location: Optional[str] = None             # e.g. "Your Location Address USA"
    logo: Optional[str] = None                 # was company_logo
    jobs: int = 0                              # e.g. "8 Open Jobs" (was open_jobs_count)

    model_config = ConfigDict(from_attributes=True)


# ── Root response ─────────────────────────────────────────────────────────────
class CandidateDashboardResponse(BaseModel):
    stat_bar: DashboardStatBar
    profile_summary: DashboardProfileSummary
    application_stats: DashboardApplicationStats
    recent_applications: List[DashboardAppliedJob]
    active_package: Optional[DashboardActivePackage] = None  # None when no active package
    job_recommendations: List[DashboardRecommendedJob]
    followings: List[DashboardFollowedCompany]

    model_config = ConfigDict(from_attributes=True)