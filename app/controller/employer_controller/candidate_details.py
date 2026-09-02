from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import recruiter_admin_only
from app.schema.common import ResponseSchema
from app.service.candidate_details_service import (
    CandidateDetailsService,
)

router = APIRouter(
    prefix="/recruiter",
    tags=["Recruiter Candidate Details"],
)


@router.get(
    "/candidates/{candidate_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(recruiter_admin_only)],
)
async def get_candidate_details(
    candidate_id: str,
    payload: dict = Depends(recruiter_admin_only),
    session: AsyncSession = Depends(get_db),
):
    result = (
        await CandidateDetailsService.get_candidate_details(
            session=session,
            candidate_id=candidate_id,
            user_id=payload.get("user_id"),
        )
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate details fetched successfully",
        data=result.model_dump() if hasattr(result, "model_dump") else result,
    )
    
