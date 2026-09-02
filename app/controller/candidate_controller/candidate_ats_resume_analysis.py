"""Candidate-only API for AI ATS resume analysis."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.ats_resume_analysis import ATSResumeAnalysisRequest, ATSResumeAnalysisResponse
from app.schema.common import ResponseSchema
from app.service.ats_resume_analysis_service import ATSResumeAnalysisService

router = APIRouter(prefix="/candidate", tags=["Candidate AI ATS Resume Analysis"])


def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


@router.post(
    "/resume/ats-analysis",
    response_model=ResponseSchema[ATSResumeAnalysisResponse],
    response_model_exclude_none=True,
    summary="Analyze a resume for ATS compatibility (AWS Bedrock)",
)
async def analyze_resume_for_ats(
    body: ATSResumeAnalysisRequest = ATSResumeAnalysisRequest(),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await ATSResumeAnalysisService().analyze(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message="ATS resume analysis completed successfully",
        data=result.model_dump(exclude_none=True),
    )
