from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.employer_dashboard_schema import EmployerAnalyticsFilters, EmployerDashboardFilters
from app.schema.common import ResponseSchema
from app.service.employer_service.dashboard_service import EmployerDashboardService


router = APIRouter(
    prefix="/employer",
    tags=["Employer Dashboard"],
)


@router.get(
    "/dashboard",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Employer dashboard",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def get_employer_dashboard(
    job_id: Optional[str] = None,
    application_status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(default=5, ge=1, le=25),
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    filters = EmployerDashboardFilters(
        job_id=job_id,
        application_status=application_status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    result = await EmployerDashboardService.get_dashboard(
        session=session,
        payload=payload,
        filters=filters,
    )
    return ResponseSchema(
        message="Employer dashboard fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/analytics",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Employer analytics",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def get_employer_analytics(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    job_id: Optional[str] = None,
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly|yearly)$"),
    department: Optional[str] = None,
    employment_type: Optional[str] = None,
    location: Optional[str] = None,
    hiring_manager: Optional[str] = None,
    status: Optional[str] = None,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    filters = EmployerAnalyticsFilters(
        from_date=from_date,
        to_date=to_date,
        job_id=job_id,
        period=period,
        department=department,
        employment_type=employment_type,
        location=location,
        hiring_manager=hiring_manager,
        status=status,
    )
    result = await EmployerDashboardService.get_analytics(
        session=session,
        payload=payload,
        filters=filters,
    )
    return ResponseSchema(
        message="Employer analytics fetched successfully.",
        data=result.model_dump(),
    )
