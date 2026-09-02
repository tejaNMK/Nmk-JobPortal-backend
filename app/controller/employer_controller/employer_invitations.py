from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.schema.invitations import EmployerInvitationFilters
from app.service.employer_service.invitations_service import EmployerInvitationsService

router = APIRouter(
    prefix="/employer",
    tags=["Employer Invitations"],
)


@router.get(
    "/invitations",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(employer_user_only)],
)
async def employer_list_invitations(
    job_id: Optional[str] = Query(default=None),
    candidate_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: str = Query(default="newest", pattern="^(newest|oldest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    filters = EmployerInvitationFilters(
        job_id=job_id,
        candidate_id=candidate_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    result = await EmployerInvitationsService.list_invitations(
        session=session,
        payload=payload,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Employer invitation history fetched successfully",
        data=result.model_dump(),
    )


