"""AI Text Assist service.

Powers the "Improve Writing / Grammar Check / Shorter" quick-actions for
resume description fields, reused as-is by Edit Profile, Build Resume, and
Start Builder (see `app/schema/ai_text_assist.py` for why this is
deliberately field-agnostic and stateless).

Uses the same reusable `AIService` (AWS Bedrock) wrapper every other AI
feature in this codebase goes through -- no separate provider integration,
no duplicated credential/timeout/error handling.

Design notes
------------
* Plain text in, plain text out. Unlike `AIProfileWriterService` this
  never asks Bedrock for JSON -- there's exactly one string to transform,
  so `AIService.ainvoke_with_usage` is used directly and its `content` is
  the answer. This keeps the happy path simple and removes an entire class
  of "invalid JSON from the model" failure modes for a feature that runs
  on every keystroke-adjacent click.
* Formatting preservation. The candidate's text arrives as newline-
  separated plain text (one line per bullet/paragraph -- see
  `htmlToPlainText` on the frontend). The prompt explicitly instructs the
  model to keep that same line structure rather than collapsing it into a
  single paragraph, since the frontend renders each line as its own
  `<div>` and a merged paragraph would visibly reformat the field.
* No fabrication. Every action instruction below is scoped to *transforming
  the given text*, never inventing new employers, skills, dates, or
  achievements -- the model only ever sees the text passed in, so it has
  nothing else to draw on regardless.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.schema.ai_text_assist import (
    AITextAssistAction,
    AITextAssistRequest,
    AITextAssistResponse,
)
from app.service.ai_service import AIService, AIServiceError, ai_error_status_code

logger = logging.getLogger(__name__)

AI_TEXT_ASSIST_FEATURE_KEY = "candidate_resume_ai_text_assist"
AI_TEXT_ASSIST_PROMPT_VERSION = "v1"

_MAX_OUTPUT_TOKENS = 900
_TEMPERATURE = 0.2

_ACTION_INSTRUCTION: dict[AITextAssistAction, str] = {
    AITextAssistAction.IMPROVE: (
        "Improve the writing: make it clearer, more impactful, and more "
        "professional. Strengthen weak or vague phrasing, tighten wordy "
        "sentences, and prefer strong action verbs (e.g. 'led', "
        "'delivered', 'reduced') over passive or filler phrases (e.g. "
        "'responsible for', 'helped to', 'worked on'). Fix any grammar or "
        "spelling issues along the way."
    ),
    AITextAssistAction.GRAMMAR: (
        "Perform a grammar check only: fix grammar, spelling, punctuation, "
        "and capitalization mistakes. Keep the candidate's own wording, "
        "sentence structure, tone, and level of detail as close to the "
        "original as possible -- do not rephrase, rewrite, or shorten "
        "anything that is already grammatically correct."
    ),
    AITextAssistAction.SHORTER: (
        "Make the text shorter and more concise. Keep only the strongest, "
        "most relevant points, tighten the language, and cut redundancy "
        "and filler -- while preserving the core meaning and every fact "
        "it contains. Aim for noticeably shorter than the original."
    ),
}


class AITextAssistService:
    """Orchestrates the AI Text Assist feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`), matching every other AI-backed service in this codebase,
    so tests/callers can supply a fake implementation without touching
    boto3/Bedrock.
    """

    def __init__(self, ai_service: AIService | None = None) -> None:
        self._ai_service = ai_service or AIService()

    async def assist(self, request: AITextAssistRequest) -> AITextAssistResponse:
        """Apply `request.action` to `request.text` and return the
        transformed text. Operates ONLY on the given text -- no candidate
        profile/resume is loaded or referenced."""

        original_text = request.text.strip()
        if not original_text:
            # Defense in depth -- the schema's `field_validator` already
            # rejects blank text, but a service consumed outside the
            # controller shouldn't rely on that alone.
            raise HTTPException(status_code=400, detail="'text' must not be blank.")

        system_prompt, user_prompt = self._build_prompt(
            original_text, request.action, request.field_label
        )

        try:
            result = await self._ai_service.ainvoke_with_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=_TEMPERATURE,
                feature=AI_TEXT_ASSIST_FEATURE_KEY,
                prompt_version=f"{AI_TEXT_ASSIST_PROMPT_VERSION}_{request.action.value}",
            )
        except AIServiceError as exc:
            logger.warning(
                "AI text assist Bedrock request failed (action=%s): %s",
                request.action.value,
                exc,
            )
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail="The AI writer is temporarily unavailable. Please try again in a moment.",
            ) from exc

        transformed = self._clean_output(result.content, fallback="")
        if not transformed:
            # `result.content` was non-empty (AIService already rejects a
            # truly empty response), but nothing usable survived cleanup --
            # e.g. the model's response was entirely reasoning preamble
            # with no answer after it. Silently returning the caller's own
            # original text here would look like a successful no-op edit;
            # surface it as a real error instead so the person knows to
            # retry rather than assuming "no changes were needed."
            logger.warning(
                "AI text assist produced no usable output after cleanup "
                "(action=%s).",
                request.action.value,
            )
            raise HTTPException(
                status_code=502,
                detail="The AI writer had trouble responding. Please try again.",
            )
        return AITextAssistResponse(text=transformed, action=request.action)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        text: str,
        action: AITextAssistAction,
        field_label: str | None,
    ) -> tuple[str, str]:
        instruction = _ACTION_INSTRUCTION[action]
        field_name = (field_label or "").strip() or "resume field"

        system_prompt = (
            "You are an expert resume editor. You are given the exact "
            "current text of ONE resume field and must transform it "
            "according to a single instruction -- nothing more. You NEVER "
            "invent employers, job titles, dates, skills, certifications, "
            "metrics, or any other fact that is not already present in the "
            "text you were given, and you never add commentary about the "
            "change.\n\n"
            f"TASK: {instruction}\n\n"
            "FORMAT: The input text may contain multiple lines (each line "
            "is one bullet point or sentence). Preserve that same line "
            "structure in your output -- the same number of lines doing "
            "the same job, each on its own line -- rather than merging "
            "everything into a single paragraph, unless the task above "
            "explicitly calls for combining or dropping lines. Do not add "
            "bullet symbols, markdown (no '**', '#', backticks), numbering, "
            "or quotation marks that were not already in the input.\n\n"
            "Respond with ONLY the transformed text and nothing else -- no "
            "preamble, no explanation, no surrounding quotes."
        )

        user_prompt_parts = [f"FIELD: {field_name}", "", "CURRENT TEXT:", text]
        user_prompt = "\n".join(user_prompt_parts)

        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Output cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_output(raw: str, *, fallback: str) -> str:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        # Strip a single layer of wrapping quotes some models add despite
        # instructions not to (e.g. '"Improved text here"').
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
            cleaned = cleaned[1:-1].strip()
        return cleaned or fallback