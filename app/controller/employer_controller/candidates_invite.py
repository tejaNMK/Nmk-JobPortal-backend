from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema, created_response
from app.schema.invitations import SendInvitationRequest

from app.service.employer_service.invitations_service import EmployerInvitationsService

router = APIRouter(
    prefix="/employer",
    tags=["Employer Invitations"],
)


@router.post(
    "/candidates/{candidate_id}/invite",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
    dependencies=[Depends(employer_user_only)],
)
async def invite_candidate_to_apply(
    candidate_id: str,
    request_body: SendInvitationRequest,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    invitation = await EmployerInvitationsService.send_invitation(
        session=session,
        payload=payload,
        candidate_id=candidate_id,
        request=request_body,
        message=request_body.message,
    )
    return created_response(
        message="Invitation sent successfully",
        data={"invitation_id": invitation.invitation_id, "status": invitation.status},
    )

