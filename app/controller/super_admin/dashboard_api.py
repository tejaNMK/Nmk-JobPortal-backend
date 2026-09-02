from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse
from io import BytesIO

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.schema.common import ResponseSchema, success_response
from app.schema.super_admin.dashboard_api import SuperAdminJobBulkActionRequest
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.super_admin.company_approval_service import CompanyApprovalService
from app.service.super_admin.dashboard_api_service import (
    SuperAdminDashboardService,
)
from app.utils.date_range import normalize_date_range

router = APIRouter(
    prefix="/super-admin",
    tags=["Super Admin Dashboard"],
    dependencies=[Depends(super_admin_only)],
)


@router.get("/recent-registrations", response_model=ResponseSchema)
@router.get("/dashboard/recent-registrations", response_model=ResponseSchema)
async def recent_registrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminDashboardService.list_recent_registrations(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        date_range=date_range,
    )

    return success_response(
        data=data.model_dump(),
        message="Recent registrations fetched successfully.",
    )


@router.get("/job-overview", response_model=ResponseSchema)
async def job_overview(
    session: AsyncSession = Depends(get_db),
):
    data = await SuperAdminDashboardService.get_job_overview(
        session=session,
    )

    return success_response(
        data=data.model_dump(),
        message="Job overview fetched successfully.",
    )


@router.get("/jobs", response_model=ResponseSchema)
async def list_jobs(
    search: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    recruiter: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    employment_type: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    work_mode: Optional[str] = Query(default=None),
    experience_level: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    salary_min: Optional[float] = Query(default=None),
    salary_max: Optional[float] = Query(default=None),
    posted_date: Optional[datetime] = Query(default=None),
    expiry_date: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query(default="posted_date"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminDashboardService.list_jobs(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        company=company,
        recruiter=recruiter,
        location=location,
        status=status,
        employment_type=employment_type or job_type,
        work_mode=work_mode,
        experience_level=experience_level,
        industry=industry,
        salary_min=salary_min,
        salary_max=salary_max,
        posted_date=posted_date,
        expiry_date=expiry_date,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return success_response(
        data=data.model_dump(),
        message="Jobs fetched successfully.",
    )


@router.patch("/jobs/bulk-action", response_model=ResponseSchema)
async def bulk_action_jobs(
    request: SuperAdminJobBulkActionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await SuperAdminDashboardService.bulk_action_jobs(
        session=session,
        job_ids=request.job_ids,
        action=request.action,
        actor=payload,
        reason=request.reason,
    )

    return success_response(
        data=data.model_dump(),
        message="Bulk job action completed successfully.",
    )


@router.delete("/jobs/{job_id}", response_model=ResponseSchema)
async def delete_job(
    job_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await SuperAdminDashboardService.bulk_action_jobs(
        session=session,
        job_ids=[job_id],
        action="delete",
        actor=payload,
    )
    if data.updated == 0:
        raise HTTPException(status_code=404, detail="Job not found.")

    return success_response(
        data=data.model_dump(),
        message="Job deleted successfully.",
    )


@router.get("/jobs/export")
async def export_jobs(
    export_format: str = Query(default="csv", pattern="^(csv|excel|pdf|CSV|EXCEL|PDF)$"),
    search: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    recruiter: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    employment_type: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    work_mode: Optional[str] = Query(default=None),
    experience_level: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    salary_min: Optional[float] = Query(default=None),
    salary_max: Optional[float] = Query(default=None),
    posted_date: Optional[datetime] = Query(default=None),
    expiry_date: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    sort_by: str = Query(default="posted_date"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    content, filename, media_type = await SuperAdminDashboardService.export_jobs(
        session=session,
        export_format=export_format,
        actor=payload,
        search=search,
        company=company,
        recruiter=recruiter,
        location=location,
        status=status,
        employment_type=employment_type or job_type,
        work_mode=work_mode,
        experience_level=experience_level,
        industry=industry,
        salary_min=salary_min,
        salary_max=salary_max,
        posted_date=posted_date,
        expiry_date=expiry_date,
        date_range=date_range,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/logs", response_model=ResponseSchema)
async def activity_logs(
    action: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    user_role: Optional[str] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    range_start = start_date or from_date
    range_end = end_date or to_date
    date_range = (
        normalize_date_range(
            from_date=range_start,
            to_date=range_end,
            timezone_name=timezone,
        )
        if range_start is not None or range_end is not None
        else None
    )
    data = await ActivityLogService.list_logs(
        session=session,
        page=page,
        page_size=page_size,
        action=action,
        actor=actor,
        role=role or user_role,
        entity_type=entity_type,
        search=search,
        start_date=None,
        end_date=None,
        date_range=date_range,
    )

    return success_response(
        data=data.model_dump(),
        message="Activity logs fetched successfully.",
    )


@router.get("/users", response_model=ResponseSchema)
async def list_users(
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    subscription: Optional[str] = Query(default=None),
    registered_from: Optional[datetime] = Query(default=None),
    registered_to: Optional[datetime] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query(default="newest", pattern="^(newest|oldest|name)$"),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminDashboardService.list_users(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        status=status,
        subscription=subscription,
        registered_from=registered_from,
        registered_to=registered_to,
        date_range=date_range,
        sort_by=sort_by,
    )

    return success_response(
        data=data.model_dump(),
        message="Users fetched successfully.",
    )


@router.get("/dashboard/latest-registrations", response_model=ResponseSchema)
async def latest_registrations(
    limit: int = Query(5, ge=5, le=10),
    role: Optional[str] = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminDashboardService.list_recent_registrations(
        session=session,
        page=1,
        page_size=limit,
        search=None,
        role=role,
        date_range=date_range,
    )
    return success_response(
        data={"items": [item.model_dump() for item in data.items]},
        message="Latest registrations fetched successfully.",
    )


@router.get("/dashboard/latest-jobs", response_model=ResponseSchema)
async def latest_jobs(
    limit: int = Query(5, ge=5, le=10),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminDashboardService.list_jobs(
        session=session,
        page=1,
        page_size=limit,
        search=None,
        company=None,
        recruiter=None,
        location=None,
        status=None,
        employment_type=None,
        work_mode=None,
        experience_level=None,
        industry=None,
        salary_min=None,
        salary_max=None,
        posted_date=None,
        expiry_date=None,
        date_range=date_range,
        sort_by="posted_date",
        sort_order="desc",
    )
    return success_response(
        data={"items": [item.model_dump() for item in data.items]},
        message="Latest jobs fetched successfully.",
    )


@router.get("/dashboard/latest-company-approvals", response_model=ResponseSchema)
async def latest_company_approvals(
    limit: int = Query(5, ge=5, le=10),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await CompanyApprovalService.latest_company_approvals(
        session=session,
        limit=limit,
        date_range=date_range,
    )
    return success_response(
        data=data.model_dump(),
        message="Latest company approvals fetched successfully.",
    )


@router.get("/dashboard/latest-logs", response_model=ResponseSchema)
async def latest_logs(
    limit: int = Query(5, ge=5, le=10),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = (
        normalize_date_range(
            from_date=from_date,
            to_date=to_date,
            timezone_name=timezone,
        )
        if from_date is not None or to_date is not None
        else None
    )
    data = await ActivityLogService.list_logs(
        session=session,
        page=1,
        page_size=limit,
        action=None,
        actor=None,
        role=None,
        entity_type=None,
        search=None,
        start_date=None,
        end_date=None,
        date_range=date_range,
    )
    return success_response(
        data={"items": [item.model_dump() for item in data.items]},
        message="Latest logs fetched successfully.",
    )
