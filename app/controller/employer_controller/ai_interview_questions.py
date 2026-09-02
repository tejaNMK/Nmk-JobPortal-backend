from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.schema.employer_ai_interview_question import (
    EmployerInterviewQuestionsRequest,
)
from app.service.employer_service.ai_interview_question_service import (
    EmployerAIInterviewQuestionService,
)


router = APIRouter(
    prefix="/employer/jobs",
    tags=["Employer AI Interview Questions"],
)


@router.post(
    "/{job_id}/candidates/{candidate_id}/ai-interview-questions",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Generate AI interview questions for an employer-owned job and visible candidate",
)
async def generate_employer_ai_interview_questions(
    job_id: str,
    candidate_id: str,
    request_body: EmployerInterviewQuestionsRequest = EmployerInterviewQuestionsRequest(),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await EmployerAIInterviewQuestionService.generate_questions(
        session=session,
        payload=payload,
        job_id=job_id,
        candidate_id=candidate_id,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI interview questions generated successfully",
        data=result.model_dump(),
    )
