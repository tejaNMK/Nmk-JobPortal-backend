from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema, success_response
from app.schema.super_admin.employer import (
    EmployerStatusRequest,
    EmployerUpdateRequest,
    EmployerVerificationRequest,
)
from app.service.super_admin.employer_service import EmployerService
from app.dependencies.role_dependencies import super_admin_only

router = APIRouter(
    prefix="/super-admin/employers",
    tags=["Super Admin Employers"],
    dependencies=[Depends(super_admin_only)],

)


@router.get(
    "",
    response_model=ResponseSchema,
)
async def list_employers(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|registered_date|newest|oldest|name|company_name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):

    data = await EmployerService.list_employers(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return success_response(
        data=data.model_dump(),
        message="Employers fetched successfully.",
    )


@router.get(
    "/{employer_id}",
    response_model=ResponseSchema,
)
async def get_employer(
    employer_id: str,
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.get_employer(
        session=session,
        employer_id=employer_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Employer fetched successfully.",
    )


@router.put(
    "/{employer_id}",
    response_model=ResponseSchema,
)
async def update_employer(
    employer_id: str,
    request: EmployerUpdateRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.update_employer(
        session=session,
        employer_id=employer_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Employer updated successfully.",
    )


@router.patch(
    "/{employer_id}/status",
    response_model=ResponseSchema,
)
async def update_employer_status(
    employer_id: str,
    request: EmployerStatusRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.update_employer_status(
        session=session,
        employer_id=employer_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Employer status updated successfully.",
    )


@router.patch(
    "/{employer_id}/approve",
    response_model=ResponseSchema,
)
async def approve_employer_company(
    employer_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.approve_employer_company(
        session=session,
        employer_id=employer_id,
        actor=payload,
    )

    return success_response(
        data=data.model_dump(),
        message="Company approved successfully.",
    )


@router.patch(
    "/{employer_id}/verify",
    response_model=ResponseSchema,
)
async def verify_employer(
    employer_id: str,
    request: EmployerVerificationRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.verify_employer(
        session=session,
        employer_id=employer_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Employer verification updated successfully.",
    )


@router.delete(
    "/{user_id}",
    response_model=ResponseSchema,
)
async def delete_employer(
    user_id: UUID,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerService.delete_employer(
        session=session,
        user_id=user_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Employer account deleted successfully.",
    )


@router.patch(
    "/{user_id}/make-admin",
    response_model=ResponseSchema,
)
async def make_admin(
    user_id: UUID,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await EmployerService.make_admin(
        session=session,
        user_id=user_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Employer promoted successfully.",
    )

@router.patch(
    "/{user_id}/remove-admin",
    response_model=ResponseSchema,
)
async def remove_admin(
    user_id: UUID,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await EmployerService.remove_admin(
        session=session,
        user_id=user_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Admin access removed successfully.",
    )
