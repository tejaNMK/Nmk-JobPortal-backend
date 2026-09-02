from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


EmployerApplicationStatus = Literal[
    "REJECTED",
    "SHORTLISTED",
    "APPLIED",
    "REVIEW",
    "INTERVIEW",
    "INTERVIEW_SCHEDULED",
    "ON_HOLD",
    "OFFER",
    "HIRED",
    "ARCHIVED",
]


class ApplicantFilterParams(BaseModel):
    job_id: Optional[str] = None
    search: Optional[str] = None
    status: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: str = "desc"
    ai_rank: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ApplicantListItem(BaseModel):
    application_id: str
    candidate_id: str
    applicant_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_image_url: Optional[str] = None
    current_designation: Optional[str] = None
    total_experience: Optional[float] = None
    applied_position: str
    job_id: str
    referral_contact: Optional[str] = None
    source: Optional[str] = None
    resume_name: Optional[str] = None
    has_resume: bool = False
    view_profile_url: str
    view_resume_url: Optional[str] = None
    download_resume_url: Optional[str] = None
    application_date: datetime
    application_status: str
    match_score: Optional[float] = None
    match_label: Optional[str] = None
    match_reasons: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ApplicantListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ApplicantListItem]


class ApplicantProfileResponse(BaseModel):
    application_id: str
    candidate_id: str

    applicant_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None

    headline: Optional[str] = None
    summary: Optional[str] = None
    total_experience: Optional[float] = None

    current_location: Optional[str] = None
    preferred_location: Optional[str] = None

    skills_summary: Optional[str] = None
    profile_image_url: Optional[str] = None
    current_designation: Optional[str] = None

    job_id: str
    applied_position: str

    application_status: str
    application_date: datetime

    referral_contact: Optional[str] = None
    source: Optional[str] = None

    resume_name: Optional[str] = None
    has_resume: bool = False
    view_profile_url: str
    view_resume_url: Optional[str] = None
    download_resume_url: Optional[str] = None
    match_score: Optional[float] = None
    match_label: Optional[str] = None
    match_reasons: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EmployerApplicationStatusUpdateRequest(BaseModel):
    status: EmployerApplicationStatus
    reason: Optional[str] = Field(default=None, max_length=2000)


class EmployerApplicationStatusUpdateResponse(BaseModel):
    application_id: str
    job_id: str
    candidate_id: str
    previous_status: str
    application_status: str
    updated_at: str


class ResumeDownloadResponse(BaseModel):
    resume_id: str
    file_name: Optional[str]
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    is_previewable: bool = False
    url: str
    preview_url: str
    download_url: str
