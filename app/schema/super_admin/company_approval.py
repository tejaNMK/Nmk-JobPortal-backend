from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyApprovalItem(BaseModel):
    company_id: str
    company_uuid: UUID
    company_name: str
    employer_id: str
    employer_user_id: UUID
    employer_name: str
    employer_email: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    verification_status: str
    rejection_reason: Optional[str] = None
    submitted_at: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None


class CompanyApprovalListResponse(BaseModel):
    items: List[CompanyApprovalItem]
    total: int
    page: int
    page_size: int


class CompanyApprovalActionResponse(BaseModel):
    company_id: str
    verification_status: str
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class CompanyRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class CompanyApprovalFilters(BaseModel):
    search: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int
    page_size: int
    sort_by: str
    sort_order: str


class LatestCompanyApprovalItem(BaseModel):
    company_id: str
    company_name: str
    employer_name: str
    verification_status: str
    submitted_at: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None


class LatestCompanyApprovalResponse(BaseModel):
    items: List[LatestCompanyApprovalItem]


class CompanyApprovalHistoryItem(CompanyApprovalItem):
    action_date: Optional[Any] = None
