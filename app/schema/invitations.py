from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


class CandidateInvitationStatus(str):
    PENDING = "PENDING"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


InvitationStatusValue = Literal["accepted", "declined"]


class CandidateSummary(BaseModel):
    candidate_id: str
    full_name: str
    profile_photo: Optional[str] = None
    profile_headline: Optional[str] = None
    profile_completion: Optional[int] = None
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    experience: Optional[float] = None
    years_of_experience: Optional[float] = None
    location: Optional[str] = None
    top_skills: List[str] = []
    highest_education: Optional[str] = None
    education_summary: Optional[str] = None
    resume_available: bool = False
    open_to_work: bool = False
    expected_salary: Optional[str] = None
    notice_period: Optional[str] = None
    availability: Optional[str] = None
    profile_completion_percentage: Optional[int] = None
    last_updated: Optional[datetime] = None


class CandidateSearchRequest(BaseModel):
    keyword: Optional[str] = None
    skills: List[str] = []
    experience_min: Optional[float] = None
    experience_max: Optional[float] = None
    location: Optional[str] = None
    preferred_role: Optional[str] = None
    education: Optional[str] = None
    certifications: Optional[str] = None
    availability: Optional[str] = None
    employment_type: Optional[str] = None
    expected_salary: Optional[str] = None
    work_authorization: Optional[str] = None
    work_preference: Optional[str] = None
    profile_completion_min: Optional[int] = None
    updated_within_days: Optional[int] = None
    sort_by: Literal[
        "relevance",
        "newest",
        "experience",
        "profile_completion",
        "last_updated",
    ] = "relevance"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CandidateSearchResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    items: List[CandidateSummary]


class CandidateSummaryCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: str
    full_name: str
    profile_photo: Optional[str] = None
    profile_headline: Optional[str] = None
    profile_completion: Optional[int] = None
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    experience: Optional[float] = None
    years_of_experience: Optional[float] = None
    location: Optional[str] = None
    top_skills: List[str] = []
    highest_education: Optional[str] = None
    education_summary: Optional[str] = None
    resume_available: bool = False
    open_to_work: bool = False
    expected_salary: Optional[str] = None
    notice_period: Optional[str] = None
    availability: Optional[str] = None
    profile_completion_percentage: Optional[int] = None
    last_updated: Optional[datetime] = None


class ActiveJobSummary(BaseModel):
    job_id: str
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    openings: Optional[int] = None
    posted_date: Optional[datetime] = None
    application_count: Optional[int] = None


class EmployerActiveJobsResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    items: List[ActiveJobSummary]


class SendInvitationRequest(BaseModel):
    job_id: str
    message: str = Field(min_length=1, max_length=2000)


class InvitationResponse(BaseModel):
    invitation_id: str
    status: str
    job_id: Optional[str] = None
    job_details_url: Optional[str] = None
    invited_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EmployerInvitationFilters(BaseModel):
    job_id: Optional[str] = None
    candidate_id: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: Optional[Literal["newest", "oldest"]] = "newest"


class EmployerInvitationListItem(BaseModel):
    invitation_id: str
    candidate: CandidateSummaryCard
    job_title: Optional[str] = None
    status: str
    invited_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None


class EmployerInvitationListResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    items: List[EmployerInvitationListItem]


class CandidateInvitationListItem(BaseModel):
    invitation_id: str
    job_id: Optional[str] = None
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    employer_name: Optional[str] = None
    job_title: Optional[str] = None
    job_location: Optional[str] = None
    employment_type: Optional[str] = None
    invitation_message: Optional[str] = None
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    status: str


class CandidateInvitationListResponse(BaseModel):
    page: int
    page_size: int
    total_records: int
    items: List[CandidateInvitationListItem]


class CandidateInvitationEmployerDetails(BaseModel):
    employer_id: str
    company_name: Optional[str] = None
    company_logo: Optional[str] = None
    company_email: Optional[str] = None
    company_website: Optional[str] = None
    company_location: Optional[str] = None


class CandidateInvitationRecruiterDetails(BaseModel):
    recruiter_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    profile_photo: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None


class CandidateInvitationJobSummary(BaseModel):
    job_id: str
    job_title: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    work_preference: Optional[str] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: Optional[str] = None
    skills: List[str] = []
    posted_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None


class CandidateInvitationDetailsResponse(BaseModel):
    invitation_id: str
    status: str
    invitation_message: Optional[str] = None
    invited_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    employer: CandidateInvitationEmployerDetails
    company: CandidateInvitationEmployerDetails
    recruiter: CandidateInvitationRecruiterDetails
    job: CandidateInvitationJobSummary
    job_details_url: str


class RespondInvitationRequest(BaseModel):
    status: InvitationStatusValue


