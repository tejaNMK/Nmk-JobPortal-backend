from datetime import date, datetime, time
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


MAX_INTERVIEW_ROUNDS = 20
MAX_INTERVIEW_ROUND_NAME_LENGTH = 100


class InterviewMode(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class InterviewStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RESCHEDULED = "RESCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class InterviewerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = " ".join(value.strip().split())
        if not value:
            raise ValueError("Name is required.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        email = str(value).strip().lower()
        if not email:
            raise ValueError("Email is required.")
        return email


class InterviewerCreateRequest(InterviewerPayload):
    pass


class InterviewerUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None

    @field_validator("name")
    @classmethod
    def trim_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = " ".join(value.strip().split())
        if not value:
            raise ValueError("Name is required.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return value
        email = str(value).strip().lower()
        if not email:
            raise ValueError("Email is required.")
        return email


class InterviewerResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InterviewerListResponse(BaseModel):
    items: list[InterviewerResponse]
    total: int
    page: int
    page_size: int


class ScheduleInterviewRequest(BaseModel):
    interview_title: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    round_number: Optional[int] = Field(default=None, ge=1, le=MAX_INTERVIEW_ROUNDS)

    interview_round: str = Field(min_length=1, max_length=MAX_INTERVIEW_ROUND_NAME_LENGTH)

    interview_date: Optional[date] = None

    interview_time: Optional[time] = None

    start_time: Optional[time] = None

    end_time: Optional[time] = None

    timezone: str = Field(default="UTC", max_length=100)

    mode: InterviewMode

    meeting_link: Optional[HttpUrl] = None

    interview_location: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    interviewer_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    interviewer_ids: Optional[list[UUID]] = None

    interviewer_emails: Optional[list[EmailStr]] = None

    interviewers: Optional[list[InterviewerPayload]] = None

    scheduled_start: Optional[datetime] = None

    scheduled_end: Optional[datetime] = None

    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_mode_fields(self):

        if self.scheduled_start is not None:
            self.interview_date = self.scheduled_start.date()
            self.start_time = self.scheduled_start.timetz().replace(tzinfo=None)
            self.interview_time = self.start_time
            if self.scheduled_start.tzinfo is not None:
                self.timezone = str(self.scheduled_start.tzinfo)

        if self.scheduled_end is not None:
            self.end_time = self.scheduled_end.timetz().replace(tzinfo=None)

        self.interview_round = " ".join(self.interview_round.strip().split())
        if not self.interview_round:
            raise ValueError("Interview round name is required.")

        if (
            self.mode == InterviewMode.ONLINE
            and not self.meeting_link
        ):
            raise ValueError(
                "Meeting Link is required for online interviews."
            )

        if (
            self.mode == InterviewMode.OFFLINE
            and not self.interview_location
        ):
            raise ValueError(
                "Interview Location is required for offline interviews."
            )

        if self.interview_date is None:
            raise ValueError("Interview date is required.")

        if self.end_time is None:
            raise ValueError("End time is required.")

        if self.interview_date < date.today():
            raise ValueError(
                "Interview date cannot be in the past."
            )

        if self.start_time is None and self.interview_time is None:
            raise ValueError("Start time is required.")

        if self.start_time is None:
            self.start_time = self.interview_time

        if self.interview_time is None:
            self.interview_time = self.start_time

        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time.")

        if (
            not self.interviewer_ids
            and not self.interviewer_emails
            and not self.interviewers
        ):
            raise ValueError("At least one interviewer is required.")

        if (
            self.interviewer_ids
            and len(set(self.interviewer_ids)) != len(self.interviewer_ids)
        ):
            raise ValueError("Duplicate interviewers are not allowed in the same round.")

        if self.interviewer_emails:
            unique_emails = list(
                dict.fromkeys(
                    str(email).strip().lower()
                    for email in self.interviewer_emails
                )
            )
            self.interviewer_emails = unique_emails

        if self.interviewers:
            unique_interviewers = {}
            for interviewer in self.interviewers:
                unique_interviewers[interviewer.email] = interviewer
            self.interviewers = list(unique_interviewers.values())

        return self


class UpdateInterviewRequest(BaseModel):
    interview_title: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    round_number: Optional[int] = Field(default=None, ge=1, le=MAX_INTERVIEW_ROUNDS)

    interview_round: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_INTERVIEW_ROUND_NAME_LENGTH,
    )

    interview_date: Optional[date] = None

    interview_time: Optional[time] = None

    start_time: Optional[time] = None

    end_time: Optional[time] = None

    timezone: Optional[str] = Field(default=None, max_length=100)

    mode: Optional[InterviewMode] = None

    meeting_link: Optional[HttpUrl] = None

    interview_location: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    interviewer_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    interviewer_ids: Optional[list[UUID]] = None

    interviewer_emails: Optional[list[EmailStr]] = None

    interviewers: Optional[list[InterviewerPayload]] = None

    scheduled_start: Optional[datetime] = None

    scheduled_end: Optional[datetime] = None

    status: Optional[InterviewStatus] = None

    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_mode_fields(self):

        if (
            self.mode == InterviewMode.ONLINE
            and self.meeting_link is None
        ):
            raise ValueError(
                "Meeting Link is required for online interviews."
            )

        if (
            self.mode == InterviewMode.OFFLINE
            and self.interview_location is None
        ):
            raise ValueError(
                "Interview Location is required for offline interviews."
            )

        if self.interview_round is not None:
            self.interview_round = " ".join(self.interview_round.strip().split())
            if not self.interview_round:
                raise ValueError("Interview round name is required.")

        if self.scheduled_start is not None:
            self.interview_date = self.scheduled_start.date()
            self.start_time = self.scheduled_start.timetz().replace(tzinfo=None)
            self.interview_time = self.start_time
            if self.timezone is None and self.scheduled_start.tzinfo is not None:
                self.timezone = str(self.scheduled_start.tzinfo)

        if self.scheduled_end is not None:
            self.end_time = self.scheduled_end.timetz().replace(tzinfo=None)

        if (
            self.interview_date
            and self.interview_date < date.today()
        ):
            raise ValueError(
                "Interview date cannot be in the past."
            )

        if self.start_time is None and self.interview_time is not None:
            self.start_time = self.interview_time

        if self.interview_time is None and self.start_time is not None:
            self.interview_time = self.start_time

        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("End time must be after start time.")

        if (
            self.interviewer_ids is not None
            and len(set(self.interviewer_ids)) != len(self.interviewer_ids)
        ):
            raise ValueError("Duplicate interviewers are not allowed in the same round.")

        if self.interviewer_emails is not None:
            self.interviewer_emails = list(
                dict.fromkeys(
                    str(email).strip().lower()
                    for email in self.interviewer_emails
                )
            )

        if self.interviewers is not None:
            unique_interviewers = {}
            for interviewer in self.interviewers:
                unique_interviewers[interviewer.email] = interviewer
            self.interviewers = list(unique_interviewers.values())

        return self


class ScheduleInterviewRoundsRequest(BaseModel):
    rounds: list[ScheduleInterviewRequest] = Field(max_length=MAX_INTERVIEW_ROUNDS)

    @model_validator(mode="after")
    def validate_rounds(self):
        if not self.rounds:
            raise ValueError("At least one interview round is required.")

        if len(self.rounds) > MAX_INTERVIEW_ROUNDS:
            raise ValueError("A maximum of 20 interview rounds is allowed.")

        round_numbers = [
            round_request.round_number
            for round_request in self.rounds
            if round_request.round_number is not None
        ]
        if len(round_numbers) != len(set(round_numbers)):
            raise ValueError("Round numbers must be unique.")

        return self


class AssignedInterviewerResponse(BaseModel):
    id: str
    name: str
    email: str
    user_id: Optional[str] = None
    role: Optional[str] = None


class InterviewerLookupItem(BaseModel):
    id: str
    name: str
    email: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class InterviewerLookupResponse(BaseModel):
    items: list[InterviewerLookupItem]
    total: int
    page: int
    page_size: int


class InterviewResponse(BaseModel):
    interview_id: str

    application_id: str

    interview_title: Optional[str]

    round_number: Optional[int]

    interview_round: str

    interview_date: date

    interview_time: time

    start_time: time

    end_time: Optional[time]

    timezone: Optional[str]

    mode: InterviewMode

    meeting_link: Optional[str]

    interview_location: Optional[str]

    interviewer_name: Optional[str]

    assigned_interviewers: list[AssignedInterviewerResponse] = []

    status: InterviewStatus

    remarks: Optional[str]

    created_at: Optional[str]

    updated_at: Optional[str]

    completed_at: Optional[str] = None

    resume_attached: bool = False

    resume_status: str = "not_provided"


class InterviewRoundsResponse(BaseModel):
    interviews: list[InterviewResponse]
    next_round_number: int
