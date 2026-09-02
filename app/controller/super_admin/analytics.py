from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.schema.common import ResponseSchema, success_response
from app.service.super_admin.analytics_service import SuperAdminAnalyticsService
from app.utils.date_range import normalize_date_range

router = APIRouter(
    prefix="/super-admin/analytics",
    tags=["Super Admin Analytics"],
    dependencies=[Depends(super_admin_only)],
)


@router.get("/dashboard", response_model=ResponseSchema)
async def dashboard_analytics(
    months: int = Query(12, ge=1, le=36),
    range_filter: str | None = Query(
        default=None,
        alias="range",
        pattern="^(last_7_days|last_30_days|last_90_days|last_6_months|last_12_months|all_time|7_days|30_days|90_days|6_months|12_months|all|alltime)$",
    ),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminAnalyticsService.get_dashboard_analytics(
        session=session,
        months=months,
        range_filter=range_filter,
        date_range=date_range,
    )
    return success_response(
        data=data.model_dump(),
        message="Dashboard analytics fetched successfully.",
    )


@router.get("/users", response_model=ResponseSchema)
async def user_distribution(
    session: AsyncSession = Depends(get_db),
):
    data = await SuperAdminAnalyticsService.get_user_distribution(session=session)
    return success_response(
        data=data.model_dump(),
        message="User distribution fetched successfully.",
    )


@router.get("/jobs", response_model=ResponseSchema)
async def job_analytics(
    months: int = Query(12, ge=1, le=36),
    range_filter: str | None = Query(
        default=None,
        alias="range",
        pattern="^(last_7_days|last_30_days|last_90_days|last_6_months|last_12_months|all_time|7_days|30_days|90_days|6_months|12_months|all|alltime)$",
    ),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminAnalyticsService.get_job_analytics(
        session=session,
        months=months,
        range_filter=range_filter,
        date_range=date_range,
    )
    return success_response(
        data=data.model_dump(),
        message="Job analytics fetched successfully.",
    )


@router.get("/registrations", response_model=ResponseSchema)
async def registration_trends(
    months: int = Query(12, ge=1, le=36),
    range_filter: str | None = Query(
        default=None,
        alias="range",
        pattern="^(last_7_days|last_30_days|last_90_days|last_6_months|last_12_months|all_time|7_days|30_days|90_days|6_months|12_months|all|alltime)$",
    ),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(from_date=from_date, to_date=to_date, timezone_name=timezone)
    data = await SuperAdminAnalyticsService.get_registration_trends(
        session=session,
        months=months,
        range_filter=range_filter,
        date_range=date_range,
    )
    return success_response(
        data=data.model_dump(),
        message="Registration trends fetched successfully.",
    )
