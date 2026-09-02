from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema, success_response
from app.schema.super_admin.candidate import (
    CandidateStatusRequest,
    CandidateUpdateRequest,
)
from app.service.super_admin.candidate_service import CandidateService
from app.dependencies.role_dependencies import super_admin_only

router = APIRouter(
    prefix="/super-admin/candidates",
    tags=["Super Admin Candidates"],
    dependencies=[Depends(super_admin_only)],
)


@router.get(
    "",
    response_model=ResponseSchema,
)
async def list_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    subscription: str | None = None,
    registered_from: datetime | None = None,
    registered_to: datetime | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|registered_on|newest|oldest|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc|ASC|DESC)$"),
    session: AsyncSession = Depends(get_db),
):

    data = await CandidateService.list_candidates(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        subscription=subscription,
        registered_from=registered_from,
        registered_to=registered_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return success_response(
        data=data.model_dump(),
        message="Candidates fetched successfully.",
    )


@router.get(
    "/{candidate_id}",
    response_model=ResponseSchema,
)
async def get_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_db),
):

    data = await CandidateService.get_candidate(
        session=session,
        candidate_id=candidate_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Candidate fetched successfully.",
    )


@router.put(
    "/{candidate_id}",
    response_model=ResponseSchema,
)
async def update_candidate(
    candidate_id: str,
    request: CandidateUpdateRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CandidateService.update_candidate(
        session=session,
        candidate_id=candidate_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Candidate updated successfully.",
    )


@router.patch(
    "/{candidate_id}/status",
    response_model=ResponseSchema,
)
async def update_candidate_status(
    candidate_id: str,
    request: CandidateStatusRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CandidateService.update_candidate_status(
        session=session,
        candidate_id=candidate_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Candidate status updated successfully.",
    )


@router.delete(
    "/{candidate_id}",
    response_model=ResponseSchema,
)
async def delete_candidate(
    candidate_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CandidateService.delete_candidate(
        session=session,
        candidate_id=candidate_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Candidate deleted successfully.",
    )

@router.patch(
    "/{candidate_id}/activate",
    response_model=ResponseSchema,
)
async def activate_candidate(
    candidate_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await CandidateService.activate_candidate(
        session=session,
        candidate_id=candidate_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Candidate activated successfully.",
    )


@router.patch(
    "/{candidate_id}/deactivate",
    response_model=ResponseSchema,
)
async def deactivate_candidate(
    candidate_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await CandidateService.deactivate_candidate(
        session=session,
        candidate_id=candidate_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Candidate deactivated successfully.",
    )
