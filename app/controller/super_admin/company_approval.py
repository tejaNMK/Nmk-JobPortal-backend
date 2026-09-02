from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.schema.common import ResponseSchema, success_response
from app.schema.super_admin.company_approval import CompanyRejectRequest
from app.service.super_admin.company_approval_service import CompanyApprovalService
from app.utils.date_range import normalize_date_range

router = APIRouter(
    prefix="/super-admin/company-approvals",
    tags=["Super Admin Company Approvals"],
    dependencies=[Depends(super_admin_only)],
)


@router.get("", response_model=ResponseSchema)
async def list_company_approvals(
    search: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await CompanyApprovalService.list_company_approvals(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        company=company,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_response(
        data=data.model_dump(),
        message="Company approvals fetched successfully.",
    )


@router.get("/pending", response_model=ResponseSchema)
async def pending_company_approvals(
    search: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await CompanyApprovalService.list_pending(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        company=company,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_response(
        data=data.model_dump(),
        message="Pending company approvals fetched successfully.",
    )


@router.patch("/{company_id}/approve", response_model=ResponseSchema)
async def approve_company(
    company_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyApprovalService.approve_company(
        session=session,
        company_id=company_id,
        actor=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="Company approved successfully.",
    )


@router.patch("/{company_id}/reject", response_model=ResponseSchema)
async def reject_company(
    company_id: str,
    request: CompanyRejectRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyApprovalService.reject_company(
        session=session,
        company_id=company_id,
        reason=request.reason,
        actor=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="Company rejected successfully.",
    )


@router.get("/history", response_model=ResponseSchema)
async def company_approval_history(
    search: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query(default="action_date"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await CompanyApprovalService.list_history(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        company=company,
        status=status,
        start_date=start_date,
        end_date=end_date,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_response(
        data=data.model_dump(),
        message="Company approval history fetched successfully.",
    )
