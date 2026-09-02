from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.schema.shortlisted_candidates import (
    ShortlistedCandidateFilterParams,
    UpdateCandidateRatingRequest,
    UpdateCandidateStatusRequest,
    BulkStatusUpdateRequest,
    BulkRejectRequest,
    UpdateCandidateNotesRequest,
    ShortlistCandidateResponse,
    UnshortlistCandidateResponse,
)


from app.service.employer_service.shortlisted_candidates_service import (
    ShortlistedCandidatesService,
)

router = APIRouter(
    prefix="/employer/shortlisted-candidates",
    tags=["Shortlisted Candidates"],
    dependencies=[Depends(employer_user_only)],
)

rejected_router = APIRouter(
    prefix="/employer/rejected-candidates",
    tags=["Rejected Candidates"],
    dependencies=[Depends(employer_user_only)],
)


def get_user_id(
    payload: dict = Depends(get_jwt_payload_401),
) -> UUID:

    raw_user_id = payload.get("user_id")

    if not raw_user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing user_id in token",
        )

    return UUID(str(raw_user_id))


@router.get(
    "",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def list_shortlisted_candidates(
    search: Optional[str] = Query(
        default=None,
        max_length=100,
    ),
    status: Optional[str] = Query(
        default=None,
        max_length=50,
    ),
    job_role: Optional[str] = Query(
        default=None,
        max_length=100,
    ),

    date_from: Optional[date] = Query(
        default=None,
    ),

    date_to: Optional[date] = Query(
        default=None,
    ),
    sort_by: Optional[str] = Query(
        default=None,
    ),

    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    filters = ShortlistedCandidateFilterParams(
        search=search,
        status=status,
        job_role=job_role,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    result = (
        await ShortlistedCandidatesService.list_shortlisted_candidates(
            session=session,
            user_id=user_id,
            filters=filters,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Shortlisted candidates fetched successfully",
        data=result.model_dump(),
    )


@rejected_router.get(
    "",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def list_rejected_candidates(
    search: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None, max_length=50),
    job_role: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    filters = ShortlistedCandidateFilterParams(
        search=search,
        status=status,
        job_role=job_role,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    result = await ShortlistedCandidatesService.list_rejected_candidates(
        session=session,
        user_id=user_id,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Rejected candidates fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{application_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_shortlisted_candidate_profile(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = (
        await ShortlistedCandidatesService.get_shortlisted_candidate_profile(
            session=session,
            user_id=user_id,
            application_id=application_id,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Shortlisted candidate profile fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{application_id}/resume",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_resume(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.get_resume(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Resume fetched successfully",
        data=result.model_dump(),
    )


@router.patch(
    "/{application_id}/rating",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_rating(
    application_id: str,
    payload: UpdateCandidateRatingRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.update_rating(
        session=session,
        user_id=user_id,
        application_id=application_id,
        rating=payload.rating,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate rating updated successfully",
        data=result,
    )


@router.patch(
    "/{application_id}/status",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_status(
    application_id: str,
    payload: UpdateCandidateStatusRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.update_status(
        session=session,
        user_id=user_id,
        application_id=application_id,
        status=payload.status,
        reason=payload.reason,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate status updated successfully",
        data=result,
    )

@router.patch(
    "/bulk/status",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def bulk_update_status(
    payload: BulkStatusUpdateRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = (
        await ShortlistedCandidatesService.bulk_update_status(
            session=session,
            user_id=user_id,
            application_ids=payload.application_ids,
            status=payload.status,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Bulk status update successful",
        data=result,
    )

@router.patch(
    "/bulk/reject",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def bulk_reject(
    payload: BulkRejectRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = (
        await ShortlistedCandidatesService.bulk_reject(
            session=session,
            user_id=user_id,
            application_ids=payload.application_ids,
            reason=payload.reason,
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidates rejected successfully",
        data=result,
    )

@router.get(
    "/{application_id}/notes",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_notes(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.get_notes(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Notes fetched successfully",
        data=result,
    )

@router.post(
    "/{application_id}/shortlist",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=200,
)
async def shortlist_candidate(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.shortlist_candidate(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate shortlisted successfully",
        data=ShortlistCandidateResponse.model_validate(result).model_dump(),
    )


@router.delete(
    "/{application_id}/unshortlist",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=200,
)
async def unshortlist_candidate(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.unshortlist_candidate(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate removed from shortlist successfully",
        data=UnshortlistCandidateResponse.model_validate(result).model_dump(),
    )


@router.patch(
    "/{application_id}/notes",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_notes(
    application_id: str,
    payload: UpdateCandidateNotesRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await ShortlistedCandidatesService.update_notes(
        session=session,
        user_id=user_id,
        application_id=application_id,
        remarks=payload.remarks,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Notes updated successfully",
        data=result,
    )

