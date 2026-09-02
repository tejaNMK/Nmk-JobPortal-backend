from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import candidate_only
from app.schema.common import ResponseSchema, success_response
from app.schema.invitations import RespondInvitationRequest
from app.service.employer_service.invitations_service import CandidateInvitationsService

router = APIRouter(
    prefix="/candidate",
    tags=["Candidate Invitations"],
)


@router.get(
    "/invitations",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(candidate_only)],
)
async def candidate_list_invitations(
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: str = Query(default="newest", pattern="^(newest|oldest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    # Candidate filters: repository supports status/date_from/date_to/sort_by/page/page_size.
    filters = type(
        "CandidateInvitationFilters",
        (),
        {
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "sort_by": sort_by,
            "page": page,
            "page_size": page_size,
        },
    )()

    result = await CandidateInvitationsService.list_invitations(
        session=session,
        payload=payload,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate invitations fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/invitations/{invitation_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(candidate_only)],
)
async def candidate_get_invitation_details(
    invitation_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateInvitationsService.get_invitation_details(
        session=session,
        payload=payload,
        invitation_id=invitation_id,
    )
    return success_response(
        message="Candidate invitation fetched successfully",
        data=result.model_dump(),
    )


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(candidate_only)],
)
async def candidate_accept_invitation(
    invitation_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateInvitationsService.accept_invitation(
        session=session,
        payload=payload,
        invitation_id=invitation_id,
    )
    return success_response(
        message="Invitation accepted successfully",
        data=result.model_dump(),
    )


@router.post(
    "/invitations/{invitation_id}/reject",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(candidate_only)],
)
async def candidate_reject_invitation(
    invitation_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateInvitationsService.reject_invitation(
        session=session,
        payload=payload,
        invitation_id=invitation_id,
    )
    return success_response(
        message="Invitation rejected successfully",
        data=result.model_dump(),
    )


@router.patch(
    "/invitations/{invitation_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(candidate_only)],
)
async def candidate_respond_invitation(
    invitation_id: str,
    body: RespondInvitationRequest,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    inv = await CandidateInvitationsService.respond(
        session=session,
        payload=payload,
        invitation_id=invitation_id,
        request=body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Invitation response recorded",
        data=inv.model_dump(),
    )

