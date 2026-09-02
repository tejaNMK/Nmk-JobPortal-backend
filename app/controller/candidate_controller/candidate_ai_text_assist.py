"""AI Text Assist API.

A single, candidate-only endpoint that powers the "Improve Writing /
Grammar Check / Shorter" quick-action chips on every resume description
field -- Professional Summary, Experience Description, Project
Description, and any other free-text resume field -- reused as-is by Edit
Profile, Build Resume, and Start Builder so behavior (loading, errors,
formatting) is identical everywhere those chips appear.

Kept as its own router module, the same pattern `candidate_ai_profile_
writer.py` and `candidate_jobs.py` already use, rather than folded into
the large `candidate.py` controller.

This intentionally does NOT look up the candidate's saved profile/resume
(contrast with `candidate_ai_profile_writer.py`): it only ever transforms
the exact text the caller sends for the field currently being edited, so
it works identically for a brand-new "Start Builder" draft that has
nothing saved yet, a field mid-edit in "Build Resume", or a saved "Edit
Profile" field.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies.role_dependencies import candidate_only
from app.schema.ai_text_assist import AITextAssistRequest, AITextAssistResponse
from app.schema.common import ResponseSchema
from app.service.ai_text_assist_service import AITextAssistService

router = APIRouter(prefix="/candidate", tags=["Candidate AI Text Assist"])


@router.post(
    "/resume/ai-text-assist",
    response_model=ResponseSchema[AITextAssistResponse],
    summary="Improve Writing / Grammar Check / Shorter for any resume description field (AWS Bedrock)",
    description=(
        "Uses AWS Bedrock to transform the exact text currently in a "
        "single resume description field -- `improve` (Improve Writing), "
        "`grammar` (Grammar Check), or `shorter` (Shorter). Operates ONLY "
        "on the `text` provided in the request (the field's current, "
        "possibly-unsaved content) -- no candidate profile or resume is "
        "loaded, and nothing is persisted. Shared by Edit Profile, Build "
        "Resume, and Start Builder for every resume description field "
        "(Professional Summary, Experience Description, Project "
        "Description, etc.) via the optional `field_label`. Returns 400 "
        "if `text` is blank and 503 if the AI service is temporarily "
        "unavailable.\n\n"
        "Example response `data`:\n"
        "```json\n"
        '{ "text": "Led a 5-engineer team to deliver a payments API '
        'processing 2M+ requests/day.", "action": "improve" }\n'
        "```"
    ),
)
async def ai_text_assist(
    body: AITextAssistRequest,
    _payload: dict = Depends(candidate_only),
):
    service = AITextAssistService()
    result: AITextAssistResponse = await service.assist(body)

    return ResponseSchema(
        success=True,
        status=200,
        message=f"Text {result.action.value} applied successfully",
        data=result,
    )