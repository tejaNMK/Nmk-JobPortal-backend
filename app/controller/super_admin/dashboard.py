from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema, success_response
from app.service.super_admin.dashboard_service import DashboardService
from app.dependencies.role_dependencies import super_admin_only
from app.utils.date_range import normalize_date_range


router = APIRouter(
    prefix="/super-admin/dashboard",
    tags=["Super Admin Dashboard"],
    dependencies=[Depends(super_admin_only)],
)

@router.get("/summary", response_model=ResponseSchema)
async def get_dashboard_summary(
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    date_range = normalize_date_range(
        from_date=from_date,
        to_date=to_date,
        timezone_name=timezone,
    )

    data = await DashboardService.get_dashboard_summary(
        session=session,
        date_range=date_range,
    )

    return success_response(
        data=data.model_dump(),
        message="Dashboard summary fetched successfully.",
    )



