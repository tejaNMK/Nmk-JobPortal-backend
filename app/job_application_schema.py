from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ApplicationStatus = Literal[
    "APPLIED", "REVIEW", "INTERVIEW", "OFFER", "REJECTED", "ARCHIVED", "WITHDRAWN"
]

ApplicationSource = Literal["Jobs Portal", "Company Website", "Referral", "Recruiter", "Other"]

InterviewMode = Literal["VIDEO", "PHONE", "ONSITE"]

InterviewStatus = Literal["SCHEDULED", "COMPLETED", "CANCELLED", "RESCHEDULED"]


class JobApplicationCreateSchema(BaseModel):
    job_id: str = Field(..., description="ID of the job being applied to")
    resume_id: Optional[str] = Field(
        default=None,
        description="Optional resume_id returned by /candidate/profile/resume/upload",
    )
    cover_letter_text: Optional[str] = Field(default=None, max_length=5000)
    source: ApplicationSource = Field(default="Jobs Portal")
    referral_contact: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "paste-an-existing-job-id-here",
                "cover_letter_text": "Dear Hiring Team, I am excited to apply for this role.",
                "source": "NMK Recruitment Portal",
                "referral_contact": "gopi.reddy@nmkrecruitment.com",
            }
        }
    )

    @model_validator(mode="after")
    def validate_referral(self) -> "JobApplicationCreateSchema":
        if self.source == "Referral" and not self.referral_contact:
            raise ValueError("referral_contact is required when source is 'Referral'")
        return self


class JobApplicationStatusUpdateSchema(BaseModel):
    application_status: ApplicationStatus

    @field_validator("application_status")
    @classmethod
    def candidate_allowed_statuses(cls, v: str) -> str:
        candidate_writable = {"ARCHIVED", "WITHDRAWN"}
        if v not in candidate_writable:
            raise ValueError(f"Candidates may only set status to one of {candidate_writable}")
        return v


class NextStepUpsertSchema(BaseModel):
    next_step_text: str = Field(..., min_length=1, max_length=500)
    next_step_due: Optional[date] = Field(default=None)


class InterviewLoopDateSchema(BaseModel):
    interview_loop_date: date = Field(...)


class ApplicationNoteCreateSchema(BaseModel):
    note_text: str = Field(..., min_length=1, max_length=2000)


class ApplicationNoteUpdateSchema(BaseModel):
    note_text: str = Field(..., min_length=1, max_length=2000)


class JobApplicationFilterParams(BaseModel):
    status: Optional[ApplicationStatus] = None
    source: Optional[ApplicationSource] = None
    search: Optional[str] = Field(default=None, max_length=100)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    sort_by: Literal[
        "APPLIED_DATE_DESC",
        "APPLIED_DATE_ASC",
        "JOB_TITLE_ASC",
        "JOB_TITLE_DESC",
        "STATUS_ASC",
        "STATUS_DESC",
    ] = "APPLIED_DATE_DESC"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be after date_to")
        if self.search is not None:
            self.search = self.search.strip() or None
        return self


class InterviewResponse(BaseModel):
    interview_id: str
    scheduled_at: datetime
    mode: Optional[str] = None
    location_or_link: Optional[str] = None
    interviewer_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApplicationNoteResponse(BaseModel):
    note_id: str
    note_text: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StatusHistoryResponse(BaseModel):
    history_id: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobSummary(BaseModel):
    job_id: str
    title: str
    location: Optional[str] = None
    team: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    application_deadline: Optional[datetime] = None
    status: Optional[str] = None
    company_name: Optional[str] = None
    company_logo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobApplicationCardResponse(BaseModel):
    application_id: str
    application_status: str
    applied_at: datetime
    source: Optional[str] = None
    referral_contact: Optional[str] = None
    job: JobSummary
    interview_loop_date: Optional[date] = None
    next_step_text: Optional[str] = None
    has_notes: bool = False
    last_nudge_sent_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class JobApplicationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[JobApplicationCardResponse]


class JobApplicationDetailResponse(BaseModel):
    application_id: str
    application_status: str
    applied_at: datetime
    updated_at: datetime
    source: Optional[str] = None
    referral_contact: Optional[str] = None
    cover_letter_text: Optional[str] = None
    interview_loop_date: Optional[date] = None
    next_step_text: Optional[str] = None
    next_step_due: Optional[date] = None
    job: JobSummary
    status_history: List[StatusHistoryResponse] = []
    interviews: List[InterviewResponse] = []
    notes: List[ApplicationNoteResponse] = []

    model_config = ConfigDict(from_attributes=True)


class NextStepItemResponse(BaseModel):
    application_id: str
    job_title: str
    company_name: Optional[str] = None
    next_step_text: str
    next_step_due: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class NextStepsResponse(BaseModel):
    items: List[NextStepItemResponse]