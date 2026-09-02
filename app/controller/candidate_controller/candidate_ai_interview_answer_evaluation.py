"""AI Interview Answer Evaluation API.

Secured candidate-only endpoint that uses AWS Bedrock (via the existing
`AIService` / `AIInterviewAnswerEvaluationService`) to evaluate a
candidate's own answer to an interview question, for a job they've
applied to.

Kept as its own router module -- the same pattern
`candidate_ai_cover_letter.py` / `candidate_ai_profile_writer.py` /
`candidate_ai_text_assist.py` already use -- so this stays a clearly
separate feature from the existing AI Interview Question Generator
(`app/controller/candidate_controller/candidate_jobs.py`'s
`/jobs/{job_id}/ai-interview-questions` route, backed by
`AIInterviewQuestionService`), which this feature reuses but does not
modify.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.ai_interview_answer_evaluation import (
    AIInterviewAnswerEvaluationRequest,
    AIInterviewAnswerEvaluationResponse,
)
from app.schema.common import ResponseSchema
from app.service.ai_interview_answer_evaluation_service import (
    AIInterviewAnswerEvaluationService,
)

router = APIRouter(prefix="/candidate", tags=["Candidate AI Interview Answer Evaluation"])


# Keep this only for protected endpoints (mirrors candidate_ai_cover_letter.py).
def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


_EXAMPLE_RESPONSE_DOC = (
    "Example response `data`:\n"
    "```json\n"
    "{\n"
    '  "job_id": "b7b7...",\n'
    '  "job_title": "Senior Backend Engineer",\n'
    '  "company_name": "Globex",\n'
    '  "question": "How would you design this role\'s core service to scale?",\n'
    '  "overall_score": 72.0,\n'
    '  "technical_accuracy": 75.0,\n'
    '  "relevance": 80.0,\n'
    '  "clarity": 65.0,\n'
    '  "strengths": ["Correctly identifies caching and async I/O as levers"],\n'
    '  "areas_for_improvement": ["Answer is a list of buzzwords rather than a concrete plan", '
    '"Does not mention how you would measure success"],\n'
    '  "detailed_feedback": "The answer shows solid awareness of scaling '
    'concepts but stays generic -- it would be stronger with a specific '
    'example from your own experience and a mention of how you\'d validate '
    'the approach.",\n'
    '  "suggested_improved_answer": "I\'d start by profiling the hot paths '
    'in the service, then apply async I/O and connection pooling before '
    'considering horizontal scaling, similar to how I approached the API '
    'work at Acme Corp..."\n'
    "}\n"
    "```"
)


@router.post(
    "/interview-answer/evaluate",
    response_model=ResponseSchema[AIInterviewAnswerEvaluationResponse],
    response_model_exclude_none=True,
    summary="Evaluate a candidate's interview answer for a job (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to evaluate the logged-in candidate's own "
        "answer (`answer`) to an interview question (`question`) for a "
        "job they've applied to (`job_id`) -- grounded in the job's "
        "details and the candidate's own profile and latest resume, so "
        "the evaluation and the suggested improved answer never credit "
        "the candidate with experience or qualifications they haven't "
        "actually reported.\n\n"
        "Returns an overall 0-100 score plus three sub-scores (Technical "
        "Accuracy, Relevance, Clarity), strengths, areas for improvement, "
        "detailed feedback, and a suggested improved answer.\n\n"
        "`question` does not need to come from the AI Interview Question "
        "Generator (`GET /candidate/jobs/{job_id}/ai-interview-questions`) "
        "-- any interview question text is accepted, so a candidate can "
        "evaluate answers to questions they were actually asked "
        "elsewhere too.\n\n"
        "Requires candidate authentication. Returns 404 if the job or "
        "the candidate's profile is not found, 403 if the candidate has "
        "not applied to this job, and 502/503 if the AI service is "
        "temporarily unavailable.\n\n"
        f"{_EXAMPLE_RESPONSE_DOC}"
    ),
)
async def evaluate_interview_answer(
    body: AIInterviewAnswerEvaluationRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AIInterviewAnswerEvaluationService()
    result: AIInterviewAnswerEvaluationResponse | None = await service.evaluate_answer(
        session=session,
        user_id=user_id,
        request=body,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Job or candidate profile not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="Interview answer evaluated successfully",
        data=result,
    )