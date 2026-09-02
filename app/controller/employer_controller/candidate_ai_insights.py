from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.service.employer_service.candidate_ai_insights_service import (
    CandidateAIInsightsService,
)


router = APIRouter(
    prefix="/employer",
    tags=["Employer AI Candidate Insights"],
)


@router.get(
    "/candidates/{candidate_id}/ai-insights",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Get AI candidate insights",
    description=(
        "Generates recruiter-oriented AI insights from a candidate's NMK profile "
        "and active resume metadata/parsed sections. Insights are evidence-based, "
        "assistive, restricted to professional information available to the "
        "authenticated recruiter, and do not replace manual candidate review."
    ),
)
async def get_candidate_ai_insights(
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateAIInsightsService.get_insights(
        session=session,
        payload=payload,
        candidate_id=candidate_id,
        regenerate=False,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI candidate insights generated successfully",
        data=result.model_dump(mode="json"),
    )


@router.post(
    "/candidates/{candidate_id}/ai-insights/regenerate",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Regenerate AI candidate insights",
    description=(
        "Regenerates recruiter-oriented AI insights for a visible candidate. "
        "This bypasses the current cache but remains an assistive analysis only; "
        "it does not change applications, statuses, shortlists, ratings, "
        "messages, or interviews."
    ),
)
async def regenerate_candidate_ai_insights(
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateAIInsightsService.get_insights(
        session=session,
        payload=payload,
        candidate_id=candidate_id,
        regenerate=True,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI candidate insights generated successfully",
        data=result.model_dump(mode="json"),
    )
