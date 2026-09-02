"""AI Cover Letter Generator API.

Secured candidate-only endpoint that uses AWS Bedrock (via the existing
`AIService` / `AICoverLetterService`) to draft a cover letter for the
logged-in candidate, tailored to one specific job posting.

Kept as its own router module -- the same pattern
`candidate_ai_profile_writer.py` / `candidate_ai_text_assist.py` already
use -- so the Bedrock-backed "generative" candidate features stay easy to
find and consistent with each other's structure (auth, response envelope,
error handling). The generated `cover_letter_text` is meant to be reviewed/
edited by the candidate and then submitted as-is via the existing
`cover_letter_text` field on `POST /candidate/applications/with-resume`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.ai_cover_letter import AICoverLetterRequest, AICoverLetterResponse
from app.schema.common import ResponseSchema
from app.service.ai_cover_letter_service import AICoverLetterService

router = APIRouter(prefix="/candidate", tags=["Candidate AI Cover Letter"])


# Keep this only for protected endpoints (mirrors candidate_ai_profile_writer.py).
def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


_EXAMPLE_RESPONSE_DOC = (
    "Example response `data`:\n"
    "```json\n"
    "{\n"
    '  "cover_letter_text": "Dear Hiring Team,\\n\\nI am excited to apply '
    'for the Senior Backend Engineer role at Acme Corp...",\n'
    '  "job_id": "1f6a3c2e-...",\n'
    '  "job_title": "Senior Backend Engineer",\n'
    '  "company_name": "Acme Corp"\n'
    "}\n"
    "```"
)


@router.post(
    "/cover-letter/generate",
    response_model=ResponseSchema[AICoverLetterResponse],
    summary="Generate an AI cover letter for a job (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to draft a cover letter for the logged-in "
        "candidate, tailored to the job identified by `job_id` -- based on "
        "their existing profile and latest resume, no fabricated "
        "employers, titles, dates, or skills. Optionally accepts `tone`, "
        "`length`, and free-text `additional_notes` to steer the letter. "
        "Pass `existing_text` (the candidate's current unsaved draft) to "
        "revise that exact letter instead of drafting a new one -- e.g. "
        "after changing the tone or editing it manually. The returned "
        "`cover_letter_text` can be submitted as-is via the existing "
        "`cover_letter_text` field on "
        "`POST /candidate/applications/with-resume`. Returns 404 if the "
        "candidate profile or the job is not found, and 502/503 if the AI "
        "service is temporarily unavailable.\n\n"
        f"{_EXAMPLE_RESPONSE_DOC}"
    ),
)
async def generate_ai_cover_letter(
    body: AICoverLetterRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AICoverLetterService()
    result: AICoverLetterResponse | None = await service.generate(
        session=session,
        user_id=user_id,
        request=body,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="AI cover letter generated successfully",
        data=result,
    )