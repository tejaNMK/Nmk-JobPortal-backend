from decimal import Decimal
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


class CandidateItem(BaseModel):
    user_id: UUID
    candidate_id: str

    first_name: str
    last_name: Optional[str] = None
    full_name: Optional[str] = None

    email: Optional[str] = None
    mobile_number: Optional[str] = None
    phone: Optional[str] = None

    headline: Optional[str] = None

    total_experience: Optional[Decimal] = None

    current_location: Optional[str] = None

    profile_completion_pct: int
    resume_uploaded: bool = False
    subscription: Optional[str] = None
    created_at: Optional[datetime] = None
    registered_on: Optional[datetime] = None
    last_login: Optional[datetime] = None

    open_to_work: bool

    status: str


class CandidateListResponse(BaseModel):
    items: List[CandidateItem]

    total: int

    page: int

    page_size: int

class CandidateStatistics(BaseModel):
    applications: int
    saved_jobs: int
    job_alerts: int
    resumes: int


class CandidateUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile_number: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    current_location: Optional[str] = None
    preferred_location: Optional[str] = None
    skills_summary: Optional[str] = None
    profile_visibility: Optional[str] = None
    searchable_flag: Optional[bool] = None
    open_to_work: Optional[bool] = None


class CandidateStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = None


class CandidateDetails(BaseModel):
    user_id: UUID
    candidate_id: str

    first_name: str
    last_name: Optional[str] = None

    email: Optional[str] = None
    mobile_number: Optional[str] = None
    full_name: Optional[str] = None

    headline: Optional[str] = None
    summary: Optional[str] = None

    total_experience: Optional[Decimal] = None

    current_location: Optional[str] = None
    preferred_location: Optional[str] = None

    profile_completion_pct: int

    open_to_work: bool

    status: str
    suspension_reason: Optional[str] = None
    subscription: Optional[dict[str, Any]] = None
    verification_status: dict[str, bool]
    resume_information: List[dict[str, Any]]
    skills: Optional[Any] = None
    experience: Optional[Any] = None
    education: Optional[Any] = None
    last_login: Optional[datetime] = None

    statistics: CandidateStatistics
