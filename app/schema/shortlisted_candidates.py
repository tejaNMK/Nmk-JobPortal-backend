from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ShortlistedCandidateFilterParams(BaseModel):
    search: Optional[str] = None

    status: Optional[str] = None

    job_role: Optional[str] = None

    date_from: Optional[date] = None

    date_to: Optional[date] = None

    sort_by: Optional[str] = None

    page: int = Field(default=1, ge=1)

    page_size: int = Field(default=20, ge=1, le=100)


class ShortlistedCandidateListItem(BaseModel):
    application_id: str
    job_id: str
    candidate_id: str

    candidate_name: str

    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_image_url: Optional[str] = None

    job_role: str
    job_title: str

    referral_contact: Optional[str] = None
    source: Optional[str] = None

    resume_name: Optional[str] = None

    application_date: datetime
    applied_at: datetime
    updated_at: datetime
    date_shortlisted: Optional[datetime] = None

    status: str
    application_status: str

    rating: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ShortlistedCandidateListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ShortlistedCandidateListItem]


class ShortlistedCandidateProfileResponse(BaseModel):
    application_id: str
    job_id: str
    candidate_id: str

    candidate_name: str

    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_image_url: Optional[str] = None

    headline: Optional[str] = None
    summary: Optional[str] = None

    total_experience: Optional[float] = None

    current_location: Optional[str] = None
    preferred_location: Optional[str] = None

    skills_summary: Optional[str] = None

    job_role: str

    status: str

    application_date: datetime
    date_shortlisted: Optional[datetime] = None

    rating: Optional[int] = None

    referral_contact: Optional[str] = None
    source: Optional[str] = None

    resume_name: Optional[str] = None
    resume_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateCandidateRatingRequest(BaseModel):
    rating: int = Field(
        ge=1,
        le=5
    )


class UpdateCandidateStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = Field(default=None, max_length=2000)


class ResumeDownloadResponse(BaseModel):
    resume_id: str
    file_name: Optional[str]
    file_path: Optional[str]

class BulkStatusUpdateRequest(BaseModel):
    application_ids: List[str]

    status: str


class BulkRejectRequest(BaseModel):
    application_ids: List[str]

    reason: Optional[str] = None

class UpdateCandidateNotesRequest(BaseModel):
    remarks: str = Field(
        min_length=1,
        max_length=2000,
    )


class CandidateNotesResponse(BaseModel):
    application_id: str
    remarks: Optional[str] = None


class ShortlistCandidateResponse(BaseModel):
    application_id: str
    job_id: str
    status: str
    date_shortlisted: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UnshortlistCandidateResponse(BaseModel):
    application_id: str
    job_id: str
    status: str

    model_config = ConfigDict(from_attributes=True)

