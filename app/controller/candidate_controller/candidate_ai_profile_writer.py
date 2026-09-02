"""AI Resume / Profile Writer API.

Secured candidate-only endpoints that use AWS Bedrock (via the existing
`AIService` / `AIProfileWriterService`) to generate improved Professional
Headline, Professional Summary / About, and Experience descriptions for the
logged-in candidate's own profile.

Kept as its own router module -- the same pattern `candidate_jobs.py`
already uses for the AI Job Match Score feature -- rather than added to the
already-large `candidate.py` profile controller, so the two Bedrock-backed
"generative" candidate features stay easy to find and are consistent with
each other's structure (auth, response envelope, error handling).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.ai_profile_writer import (
    AIProfileWriterRegenerateRequest,
    AIProfileWriterRequest,
    AIProfileWriterResponse,
)
from app.schema.common import ResponseSchema
from app.service.ai_profile_writer_service import AIProfileWriterService

router = APIRouter(prefix="/candidate", tags=["Candidate AI Profile Writer"])


# Keep this only for protected endpoints (mirrors candidate_jobs.py).
def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


_EXAMPLE_RESPONSE_DOC = (
    "Example response `data` (generate-all):\n"
    "```json\n"
    "{\n"
    '  "headline": "Senior Backend Engineer | Python, FastAPI, AWS",\n'
    '  "professional_summary": "Backend engineer with 6+ years building '
    'scalable APIs and cloud-native services. Proven track record '
    'shipping high-traffic systems on AWS using Python and FastAPI, with '
    'a focus on reliability and measurable performance gains.",\n'
    '  "experience": [\n'
    "    {\n"
    '      "title": "Backend Engineer",\n'
    '      "company": "Acme Corp",\n'
    '      "description": "Built and maintained the core API platform '
    'serving 2M+ daily requests.\\nDesigned PostgreSQL schemas that cut '
    'average query latency by 35%.\\nMentored 3 junior engineers on API '
    'design best practices."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```"
)


@router.post(
    "/profile/ai-writer/generate",
    response_model=ResponseSchema[AIProfileWriterResponse],
    response_model_exclude_none=True,
    summary="Generate AI-improved profile content (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to generate improved, ATS-friendly content for "
        "the logged-in candidate's Professional Headline, Professional "
        "Summary / About, and Experience descriptions, based on their "
        "existing profile and latest resume -- no fabricated employers, "
        "titles, or skills. Optionally accepts a `target_role` to tailor "
        "the content toward; defaults to the candidate's own target "
        "role(s) on file. Returns 404 if the candidate profile is not "
        "found, and 503 if the AI service is temporarily unavailable.\n\n"
        f"{_EXAMPLE_RESPONSE_DOC}"
    ),
)
async def generate_ai_profile_content(
    body: AIProfileWriterRequest = AIProfileWriterRequest(),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AIProfileWriterService()
    result: AIProfileWriterResponse | None = await service.generate_profile_content(
        session=session,
        user_id=user_id,
        target_role=body.target_role,
        tone=body.tone,
        length=body.length,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    return ResponseSchema(
        success=True,
        status=200,
        message="AI profile content generated successfully",
        data=result.model_dump(exclude_none=True),
    )


@router.post(
    "/profile/ai-writer/regenerate",
    response_model=ResponseSchema[AIProfileWriterResponse],
    response_model_exclude_none=True,
    summary="Regenerate a single AI profile section (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to regenerate ONE section of the logged-in "
        "candidate's profile content -- `headline`, `about`, or "
        "`experience` -- without regenerating the others. Same "
        "no-fabrication guarantee and optional `target_role`/`tone`/"
        "`length` tailoring as `POST /candidate/profile/ai-writer/generate`. "
        "When the field already has text, pass `mode` "
        "('improve' | 'rewrite' | 'make_ats_friendly' | 'shorten' | "
        "'expand') plus `existing_text` (the candidate's current unsaved "
        "draft) to transform that text instead of drafting from scratch; "
        "`existing_text` is required whenever `mode` is not `generate`. "
        "Returns 404 if the candidate profile is not found, 400 if "
        "`existing_text` is missing for a transform mode, and 503 if the "
        "AI service is temporarily unavailable.\n\n"
        "Example response `data` when `section` = `headline`:\n"
        "```json\n"
        '{ "headline": "Senior Backend Engineer | Python, FastAPI, AWS" }\n'
        "```"
    ),
)
async def regenerate_ai_profile_section(
    body: AIProfileWriterRegenerateRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    service = AIProfileWriterService()
    result: AIProfileWriterResponse | None = await service.regenerate_section(
        session=session,
        user_id=user_id,
        section=body.section,
        target_role=body.target_role,
        tone=body.tone,
        length=body.length,
        mode=body.mode,
        existing_text=body.existing_text,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    return ResponseSchema(
        success=True,
        status=200,
        message=f"AI profile section '{body.section.value}' regenerated successfully",
        data=result.model_dump(exclude_none=True),
    )