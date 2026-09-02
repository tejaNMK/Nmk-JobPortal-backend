from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.service.employer_service.invitations_service import EmployerInvitationsService

router = APIRouter(
    prefix="/employer",
    tags=["Employer Jobs"],
)


@router.get(
    "/jobs/active",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(employer_user_only)],
)
async def employer_active_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = await EmployerInvitationsService.list_active_jobs(
        session=session,
        payload=payload,
        page=page,
        page_size=page_size,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Active jobs fetched successfully",
        data=result.model_dump(),
    )

