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
* Improve vs. Grammar vs. Shorter are intentionally distinct transforms,
  not three strengths of the same edit. Improve is a substantive,
  ATS-friendly rewrite (stronger verbs, restructured sentences, tighter
  flow) at a higher sampling temperature so it doesn't just settle for
  minor wording tweaks; Grammar is a narrow, low-temperature correctness
  pass that must NOT rephrase anything already correct; Shorter condenses
  without adding anything new. All three still forbid inventing facts.
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
AI_TEXT_ASSIST_PROMPT_VERSION = "v2"

_MAX_OUTPUT_TOKENS = 1600
# Bumped from 900: the Bedrock GPT-OSS model's `max_completion_tokens`
# counts its internal <reasoning> tokens *and* the visible answer out of
# the same budget. 900 was tight enough that on longer descriptions (up
# to MAX_TEXT_ASSIST_LENGTH=4000 chars) the model could get cut off
# mid-reasoning, leaving little/no room for the actual rewrite -- which
# is what caused intermittent empty/unchanged results.

# Per-action temperature. IMPROVE needs enough freedom to genuinely
# restructure sentences and vary word choice (a real rewrite, not a
# wording tweak), while GRAMMAR and SHORTER stay low/deterministic since
# they're explicitly scoped to *not* rephrase what's already correct.
_ACTION_TEMPERATURE: dict[AITextAssistAction, float] = {
    AITextAssistAction.IMPROVE: 0.4,
    AITextAssistAction.GRAMMAR: 0.1,
    AITextAssistAction.SHORTER: 0.2,
}

_ACTION_INSTRUCTION: dict[AITextAssistAction, str] = {
    AITextAssistAction.IMPROVE: (
        "Rewrite this text the way an experienced, professional resume "
        "writer would -- not a light copy-edit. The result must read as a "
        "noticeably improved, polished, ATS-friendly rewrite, not a "
        "wording tweak of the original. Requirements:\n"
        "- Open each bullet/line with a strong, varied action verb "
        "(e.g. 'led', 'delivered', 'architected', 'streamlined', "
        "'launched', 'optimized') in place of weak or passive phrasing "
        "such as 'responsible for', 'helped to', 'worked on', 'was "
        "involved in', or 'in charge of'.\n"
        "- Actively restructure sentences where it improves clarity, "
        "readability, and flow -- reorder clauses, combine or split "
        "sentences, and cut redundant or filler words. Do not simply "
        "correct grammar and leave the original sentence shape intact.\n"
        "- Use precise, professional, ATS-friendly language and industry-"
        "appropriate terminology, but ONLY terminology that describes "
        "something already stated in the original text.\n"
        "- Do NOT invent or add any technology, tool, methodology, "
        "achievement, metric, number, responsibility, or skill that is "
        "not already present in the original text. If the original has "
        "no numbers, do not add any. You may only rephrase, reorganize, "
        "and sharpen what is already there.\n"
        "- Preserve every fact from the original -- do not drop or alter "
        "any responsibility, employer, tool, or detail that was "
        "mentioned.\n"
        "- Keep the overall length approximately the same as the "
        "original (a modest reduction is fine if it strengthens "
        "clarity); do not pad the text or add filler to reach a target "
        "length."
    ),
    AITextAssistAction.GRAMMAR: (
        "Perform a grammar check only: fix grammar, spelling, punctuation, "
        "and capitalization mistakes. Keep the candidate's own wording, "
        "sentence structure, tone, and level of detail as close to the "
        "original as possible -- do not rephrase, rewrite, restructure "
        "sentences, swap in stronger verbs, or shorten anything that is "
        "already grammatically correct. This is narrower than 'Improve': "
        "only touch what is actually a grammar/spelling/punctuation error."
    ),
    AITextAssistAction.SHORTER: (
        "Make the text MEANINGFULLY, VISIBLY shorter -- not a superficial "
        "reword that comes back roughly the same length. Cut redundancy, "
        "filler words, and weaker/lower-value points, keeping only the "
        "strongest, most relevant content and every fact it contains. You "
        "ARE explicitly permitted -- and encouraged, where it helps -- to "
        "merge two lines into one or drop an entire line/bullet if it is "
        "redundant or clearly weaker than the others; do not preserve "
        "every original line just to keep the same line count, and do "
        "not settle for only trimming a word or two per line. The output "
        "must end up with a noticeably lower word count than the input "
        "(unless the input is already a single short sentence with "
        "nothing left to cut). Do not invent any new detail, achievement, "
        "or number to fill the space -- only condense what is already "
        "there."
    ),
}

_SHORTER_RETRY_REMINDER = (
    "REMINDER: your previous attempt at this came back roughly the same "
    "length as the input -- that is not acceptable. This time, actually "
    "cut the length: remove at least one redundant phrase, clause, or "
    "line rather than just lightly rewording. The result must have a "
    "clearly lower word count than the original text."
)


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

        result = await self._invoke(
            system_prompt, user_prompt, request.action, retry=False
        )
        transformed = self._clean_output(result.content, fallback="")
        if not transformed:
            # `result.content` was non-empty (AIService already rejects a
            # truly empty response), but nothing usable survived cleanup --
            # e.g. the model's response was entirely an unterminated
            # <reasoning> block, or just a code fence/quotes with nothing
            # inside. Silently falling back to the caller's own original
            # text here would look like a successful no-op edit (the bug
            # behind "sometimes I click Improve/Shorter and nothing
            # changes") -- surface it as a real, visible error instead so
            # the person knows to retry rather than assuming "no changes
            # were needed."
            logger.warning(
                "AI text assist produced no usable output after cleanup "
                "(action=%s).",
                request.action.value,
            )
            raise HTTPException(
                status_code=502,
                detail="The AI writer had trouble responding. Please try again.",
            )

        if request.action == AITextAssistAction.SHORTER and not self._is_actually_shorter(
            original_text, transformed
        ):
            # The model sometimes returns near-identical text for already-
            # terse resume bullets -- especially at this action's low,
            # deterministic temperature -- which looks to the candidate
            # like the "Shorter" chip silently did nothing. One retry with
            # an explicit reminder that the first attempt wasn't shorter
            # resolves this in practice; if the retry still isn't shorter,
            # keep its output anyway (it's still a valid rewrite) rather
            # than erroring on a feature that otherwise worked.
            logger.info(
                "Shorter output wasn't meaningfully shorter than the "
                "input; retrying once with a stronger reminder."
            )
            retry_result = await self._invoke(
                system_prompt, user_prompt, request.action, retry=True
            )
            retry_transformed = self._clean_output(retry_result.content, fallback="")
            if retry_transformed:
                transformed = retry_transformed

        return AITextAssistResponse(text=transformed, action=request.action)

    async def _invoke(
        self,
        system_prompt: str,
        user_prompt: str,
        action: AITextAssistAction,
        *,
        retry: bool,
    ):
        """Single Bedrock call, shared by the first attempt and (for
        SHORTER only) the not-actually-shorter retry."""

        if retry:
            system_prompt = "\n\n".join([system_prompt, _SHORTER_RETRY_REMINDER])

        try:
            return await self._ai_service.ainvoke_with_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=_ACTION_TEMPERATURE[action],
                feature=AI_TEXT_ASSIST_FEATURE_KEY,
                prompt_version=(
                    f"{AI_TEXT_ASSIST_PROMPT_VERSION}_{action.value}"
                    + ("_retry" if retry else "")
                ),
            )
        except AIServiceError as exc:
            logger.warning(
                "AI text assist Bedrock request failed (action=%s, retry=%s): %s",
                action.value,
                retry,
                exc,
            )
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail="The AI writer is temporarily unavailable. Please try again in a moment.",
            ) from exc

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

    # ------------------------------------------------------------------
    # Shorter-specific effectiveness check
    # ------------------------------------------------------------------

    @staticmethod
    def _is_actually_shorter(original: str, transformed: str) -> bool:
        """True if `transformed` is a genuine shortening of `original`,
        not a (near-)identical echo. Catches the common failure mode
        where the model, given already-terse resume bullets, returns the
        input back with little or no real trimming -- which looks to the
        candidate like the Shorter chip did nothing."""

        original_norm = " ".join(original.split())
        transformed_norm = " ".join(transformed.split())
        if transformed_norm == original_norm:
            return False

        original_words = original_norm.split()
        transformed_words = transformed_norm.split()
        if len(original_words) <= 8:
            # Already terse -- there may be nothing left to cut. A
            # genuine reword (already confirmed above to differ) counts.
            return True
        return len(transformed_words) <= len(original_words) * 0.92