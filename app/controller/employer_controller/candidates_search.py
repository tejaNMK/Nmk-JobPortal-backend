from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.schema.invitations import CandidateSearchRequest
from app.service.employer_service.candidate_search_service import (
    EmployerCandidateSearchService,
)


router = APIRouter(
    prefix="/employer",
    tags=["Employer Candidates"],
)


@router.get(
    "/candidates",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def employer_search_candidates(
    keyword: Optional[str] = Query(default=None, max_length=100),
    search: Optional[str] = Query(default=None, max_length=100, deprecated=True),
    location: Optional[str] = Query(default=None, max_length=100),
    preferred_role: Optional[str] = Query(default=None, max_length=100),
    employment_type: Optional[str] = Query(default=None, max_length=50),
    work_preference: Optional[str] = Query(default=None, description="Remote/Onsite/Hybrid"),
    experience_min: Optional[float] = Query(default=None, ge=0),
    experience_max: Optional[float] = Query(default=None, ge=0),
    availability: Optional[str] = Query(default=None, max_length=100),
    education: Optional[str] = Query(default=None, max_length=100),
    certifications: Optional[str] = Query(default=None, max_length=100),
    expected_salary: Optional[str] = Query(default=None, max_length=100),
    work_authorization: Optional[str] = Query(default=None, max_length=100),
    profile_completion_min: Optional[int] = Query(default=None, ge=0, le=100),
    updated_within_days: Optional[int] = Query(default=None, ge=0),
    skills: Optional[List[str]] = Query(default=None, description="Repeat as ?skills=A&skills=B"),
    sort_by: str = Query(
        default="relevance",
        pattern="^(relevance|newest|experience|profile_completion|last_updated)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    payload=Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    filters = CandidateSearchRequest(
        keyword=keyword or search,
        skills=skills or [],
        experience_min=experience_min,
        experience_max=experience_max,
        location=location,
        preferred_role=preferred_role,
        education=education,
        certifications=certifications,
        availability=availability,
        employment_type=employment_type,
        expected_salary=expected_salary,
        work_authorization=work_authorization,
        work_preference=work_preference,
        profile_completion_min=profile_completion_min,
        updated_within_days=updated_within_days,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )

    result = await EmployerCandidateSearchService.search_candidates(
        session=session,
        payload=payload,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate search results",
        data={
            "items": [item.model_dump() for item in result.items],
            "page": result.page,
            "page_size": result.page_size,
            "total_records": result.total_records,
        },
    )



