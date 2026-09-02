from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


class EmployerItem(BaseModel):
    user_id: UUID
    employer_id: str

    first_name: str
    last_name: Optional[str] = None

    email: Optional[str] = None
    mobile_number: Optional[str] = None

    company_name: str
    created_at: Optional[datetime] = None
    registered_date: Optional[Any] = None
    last_login: Optional[datetime] = None
    subscription: Optional[str] = None

    email_verified: bool
    mobile_verified: bool
    verification_status: str
    company_verification_status: str
    status: str

    is_admin: bool


class EmployerListResponse(BaseModel):
    items: List[EmployerItem]
    total: int
    page: int
    page_size: int


class EmployerUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile_number: Optional[str] = None
    company_name: Optional[str] = None
    company_email: Optional[str] = None
    company_mobile: Optional[str] = None
    company_website: Optional[str] = None
    company_description: Optional[str] = None
    industry: Optional[str] = None
    company_location: Optional[str] = None
    website_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None


class EmployerStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = None


class EmployerVerificationRequest(BaseModel):
    status: str
    reason: Optional[str] = None


class EmployerDetails(BaseModel):
    user_id: UUID
    employer_id: str
    company_name: str
    company_logo: Optional[str] = None
    company_description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    recruiter_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool
    mobile_verified: bool
    verification_status: str
    company_verification_status: str
    rejection_reason: Optional[str] = None
    status: str
    suspension_reason: Optional[str] = None
    subscription: Optional[dict[str, Any]] = None
    total_jobs: int
    active_jobs: int
    closed_jobs: int
    registered_date: Optional[Any] = None
    last_login: Optional[datetime] = None
