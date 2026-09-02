from __future__ import annotations

import re
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


AI_MESSAGE_DRAFTING_FEATURE_KEY = "ai_message_drafting"
AI_MESSAGE_DRAFTS_MONTHLY_LIMIT_KEY = "ai_message_drafts_per_month"
MAX_AI_MESSAGE_INPUT_CHARS = 7000
MAX_RECRUITER_MESSAGE_CHARS = 4000
MAX_ADDITIONAL_INSTRUCTION_CHARS = 800
MAX_AI_MESSAGE_OUTPUT_CHARS = 3000


class _UpperStrEnum(StrEnum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
            for member in cls:
                if member.value == normalized:
                    return member
        return None


class AIMessageType(_UpperStrEnum):
    OUTREACH = "OUTREACH"
    JOB_INVITATION = "JOB_INVITATION"
    INTERVIEW_INVITATION = "INTERVIEW_INVITATION"
    FOLLOW_UP = "FOLLOW_UP"
    SHORTLIST_NOTIFICATION = "SHORTLIST_NOTIFICATION"
    RE_ENGAGEMENT = "RE_ENGAGEMENT"
    GENERAL = "GENERAL"


class AIMessageTone(_UpperStrEnum):
    PROFESSIONAL = "PROFESSIONAL"
    FRIENDLY = "FRIENDLY"
    CONCISE = "CONCISE"
    WARM = "WARM"


class AIMessageLength(_UpperStrEnum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    DETAILED = "DETAILED"


class AIMessageSourceContext(_UpperStrEnum):
    DISCOVERED_CANDIDATE = "DISCOVERED_CANDIDATE"
    APPLICANT = "APPLICANT"


def reject_unsafe_message_input(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text:
        return None
    unsafe_patterns = (
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"disregard\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"override\s+(the\s+)?(system|developer)\s+instructions",
        r"reveal\s+(the\s+)?(system|developer)\s+prompt",
        r"print\s+(the\s+)?(api\s+key|secret|token)",
        r"send\s+(this|the)\s+message\s+automatically",
    )
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in unsafe_patterns):
        raise ValueError("Input contains unsafe instructions")
    return text


class AIMessageDraftRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1, max_length=100)
    job_id: Optional[str] = Field(default=None, max_length=100)
    message_type: AIMessageType = AIMessageType.OUTREACH
    tone: AIMessageTone = AIMessageTone.PROFESSIONAL
    length: AIMessageLength = AIMessageLength.MEDIUM
    additional_instruction: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDITIONAL_INSTRUCTION_CHARS,
    )

    @field_validator("candidate_id", "job_id", "additional_instruction", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return reject_unsafe_message_input(value)

    @model_validator(mode="after")
    def validate_size(self):
        if len(self.model_dump_json(exclude_none=True)) > MAX_AI_MESSAGE_INPUT_CHARS:
            raise ValueError(
                f"AI message draft input must not exceed {MAX_AI_MESSAGE_INPUT_CHARS} characters"
            )
        return self


class AIMessageImproveRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1, max_length=100)
    job_id: Optional[str] = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=MAX_RECRUITER_MESSAGE_CHARS)
    instruction: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDITIONAL_INSTRUCTION_CHARS,
    )

    @field_validator("candidate_id", "job_id", "message", "instruction", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return reject_unsafe_message_input(value)

    @model_validator(mode="after")
    def validate_size(self):
        if len(self.model_dump_json(exclude_none=True)) > MAX_AI_MESSAGE_INPUT_CHARS:
            raise ValueError(
                f"AI message improvement input must not exceed {MAX_AI_MESSAGE_INPUT_CHARS} characters"
            )
        return self


class AIMessageDraftPayload(BaseModel):
    subject: str = Field(..., min_length=1, max_length=180)
    message: str = Field(..., min_length=1, max_length=MAX_AI_MESSAGE_OUTPUT_CHARS)

    @field_validator("subject", "message", mode="before")
    @classmethod
    def strip_text(cls, value):
        return str(value or "").strip()


class AIMessageUsageSchema(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AIMessageDraftResponse(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    message_type: AIMessageType
    source_context: AIMessageSourceContext
    subject: str
    message: str
    generated_by_ai: bool = True
    usage: AIMessageUsageSchema = Field(default_factory=AIMessageUsageSchema)


class AIMessageImproveResponse(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    message: str
    generated_by_ai: bool = True
    usage: AIMessageUsageSchema = Field(default_factory=AIMessageUsageSchema)
