from typing import Optional

from fastapi import APIRouter, Depends
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies.role_dependencies import recruiter_admin_only
from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.common import ResponseSchema

from app.config import get_db
from app.service.candidate_list_service import (
    CandidateListService,
)

router = APIRouter(
    prefix="/recruiter",
    tags=["Recruiter Candidate List"],
)


@router.get("/candidates", response_model=ResponseSchema, response_model_exclude_none=True, dependencies=[Depends(recruiter_admin_only)])
async def get_candidates(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    status: Optional[str] = None,
    skills: Optional[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateListService.get_candidates(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        skills=skills,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidates fetched successfully",
        data=result,
    )