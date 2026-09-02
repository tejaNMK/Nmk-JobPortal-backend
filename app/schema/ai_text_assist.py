"""AI Text Assist schema.

Backs the "Improve Writing / Grammar Check / Shorter" quick-action chips
that live on every resume description field -- Professional Summary,
Experience Description, Project Description, and any other free-text
resume field -- across all three places a candidate can edit that content:
Edit Profile, Build Resume, and Start Builder.

Unlike `app/schema/ai_profile_writer.py` (which loads the candidate's
saved profile/resume from the DB and drafts/regenerates a *specific*
named section such as `headline`/`about`/`experience`), this feature is
deliberately field-agnostic and stateless: it operates ONLY on the exact
text the caller sends for the field currently being edited -- including
unsaved keystrokes -- and returns the transformed text for that field
alone. No candidate profile lookup, no persistence. This is what makes it
reusable, with identical behavior, from any module/field without adding a
new backend endpoint per field.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TEXT_ASSIST_LENGTH = 4000


class AITextAssistAction(str, Enum):
    """The three quick-actions surfaced as chips under every resume
    description field. Values match the frontend's `AI_ACTIONS` keys
    (`improve` | `grammar` | `shorter`) exactly, so the client can send the
    same key it already uses locally without a translation layer."""

    IMPROVE = "improve"
    GRAMMAR = "grammar"
    SHORTER = "shorter"


class AITextAssistRequest(BaseModel):
    """Request body for `POST /candidate/resume/ai-text-assist`.

    `text` is the field's current plain-text content -- exactly what the
    candidate has typed/edited so far, not necessarily what's saved on
    their profile. `field_label` is optional free-text naming the field
    (e.g. "Professional Summary", "Experience Description", "Project
    Description") used only to tailor the prompt; it is intentionally not
    a closed enum so this endpoint stays reusable for any current or
    future resume description field without a backend change.
    """

    text: str = Field(
        min_length=1,
        max_length=MAX_TEXT_ASSIST_LENGTH,
        description="The field's current plain-text content to transform. Multi-line/bullet text is supported.",
    )
    action: AITextAssistAction = Field(
        description="Which quick-action to apply: 'improve' (Improve Writing), 'grammar' (Grammar Check), or 'shorter' (Shorter).",
    )
    field_label: str | None = Field(
        default=None,
        max_length=100,
        description="Optional human-readable field name for prompt context, e.g. 'Professional Summary', 'Experience Description', 'Project Description'.",
    )

    @field_validator("text")
    @classmethod
    def _text_must_have_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class AITextAssistResponse(BaseModel):
    """Response body: the transformed text for the same field, ready to
    replace (after user confirmation, or immediately, per the existing
    UX) the field's current content. Line breaks in `text` are
    significant -- callers should preserve them (e.g. one `<div>` per
    line) the same way they already do for the current local heuristics."""

    text: str = Field(description="AI-transformed plain text for the field.")
    action: AITextAssistAction = Field(description="Echoes the action that was applied.")

    model_config = ConfigDict(from_attributes=True)