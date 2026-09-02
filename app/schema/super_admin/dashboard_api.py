from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class RecentRegistrationItem(BaseModel):
    user_id: UUID
    full_name: str
    email: Optional[str] = None
    role: str
    status: str
    created_at: datetime


class RecentRegistrationListResponse(BaseModel):
    items: List[RecentRegistrationItem]
    total: int
    total_records: int = 0
    page: int
    page_size: int


class JobOverviewResponse(BaseModel):
    total_jobs: int
    active_jobs: int
    draft_jobs: int = 0
    closed_jobs: int = 0
    inactive_jobs: int = 0
    expired_jobs: int
    jobs_posted_today: int
    total_records: int = 0
    status_counts: Dict[str, int]


class SuperAdminJobItem(BaseModel):
    job_id: str
    job_title: str
    company_name: Optional[str] = None
    recruiter_name: Optional[str] = None
    location: Optional[str] = None
    employment_type: str
    job_type: Optional[str] = None
    work_mode: Optional[str] = None
    experience_required: Optional[str] = None
    industry: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_range: Optional[str] = None
    status: str
    posted_date: datetime
    expiry_date: Optional[datetime] = None
    created_by: Optional[str] = None


class SuperAdminJobListResponse(BaseModel):
    items: List[SuperAdminJobItem]
    total: int
    total_records: int
    page: int
    page_size: int


class SuperAdminJobBulkActionRequest(BaseModel):
    job_ids: List[str]
    action: Literal["activate", "pause", "close", "delete"]
    reason: Optional[str] = None

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value


class SuperAdminJobBulkActionResponse(BaseModel):
    action: str
    requested: int
    updated: int
    job_ids: List[str]


class ActivityLogItem(BaseModel):
    activity_log_id: UUID
    action: str
    performed_by: Optional[str] = None
    user_role: Optional[str] = None
    description: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    target_entity_name: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime
    timestamp: datetime


class ActivityLogListResponse(BaseModel):
    items: List[ActivityLogItem]
    total: int
    page: int
    page_size: int


class SuperAdminUserItem(BaseModel):
    user_id: UUID
    name: str
    email: Optional[str] = None
    role: str
    status: str
    subscription: Optional[str] = None
    registered_on: datetime
    last_login: Optional[datetime] = None


class SuperAdminUserListResponse(BaseModel):
    items: List[SuperAdminUserItem]
    total: int
    page: int
    page_size: int
