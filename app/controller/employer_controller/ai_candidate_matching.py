from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.employer_ai_candidate_matching import (
    AICandidateMatchFilters,
    AICandidateMatchRunRequest,
    MatchScope,
)
from app.schema.common import ResponseSchema
from app.service.employer_service.ai_candidate_matching_service import (
    AICandidateMatchingService,
)


router = APIRouter(
    prefix="/employer/jobs",
    tags=["AI Candidate Matching"],
)


@router.post(
    "/{job_id}/ai-match",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def generate_ai_candidate_matches(
    job_id: str,
    request: AICandidateMatchRunRequest = AICandidateMatchRunRequest(),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await AICandidateMatchingService.generate_matches(
        session=session,
        payload=payload,
        job_id=job_id,
        request=request,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI candidate matches generated successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{job_id}/ai-matches",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def list_ai_candidate_matches(
    job_id: str,
    min_score: Optional[float] = Query(default=None, ge=0, le=100),
    skills: Optional[list[str]] = Query(default=None),
    experience_min: Optional[float] = Query(default=None, ge=0),
    experience_max: Optional[float] = Query(default=None, ge=0),
    location: Optional[str] = Query(default=None, max_length=100),
    education: Optional[str] = Query(default=None, max_length=100),
    availability: Optional[str] = Query(default=None, max_length=100),
    candidate_status: Optional[str] = Query(default=None, max_length=50),
    applied: Optional[bool] = Query(default=None),
    invited: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    filters = AICandidateMatchFilters(
        min_score=min_score,
        skills=skills or [],
        experience_min=experience_min,
        experience_max=experience_max,
        location=location,
        education=education,
        availability=availability,
        candidate_status=candidate_status,
        applied=applied,
        invited=invited,
        page=page,
        page_size=page_size,
    )
    result = await AICandidateMatchingService.list_matches(
        session=session,
        payload=payload,
        job_id=job_id,
        filters=filters,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI candidate matches fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{job_id}/ai-matches/{candidate_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_ai_candidate_match_detail(
    job_id: str,
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await AICandidateMatchingService.get_match_detail(
        session=session,
        payload=payload,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI candidate match fetched successfully",
        data=result.model_dump(),
    )
