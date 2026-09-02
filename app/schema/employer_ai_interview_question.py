from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


AI_EMPLOYER_INTERVIEW_QUESTIONS_FEATURE_KEY = "ai_interview_questions"
AI_EMPLOYER_INTERVIEW_QUESTIONS_PROMPT_VERSION = "employer_interview_questions_v1"
MAX_EMPLOYER_INTERVIEW_CONTEXT_CHARS = 14000
MIN_EMPLOYER_INTERVIEW_QUESTIONS = 8
MAX_EMPLOYER_INTERVIEW_QUESTIONS = 15


class _UpperStrEnum(StrEnum):
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
            for member in cls:
                if member.value == normalized:
                    return member
        return None


class EmployerInterviewRound(_UpperStrEnum):
    SCREENING = "SCREENING"
    TECHNICAL = "TECHNICAL"
    MANAGERIAL = "MANAGERIAL"
    HR = "HR"
    FINAL = "FINAL"


class EmployerInterviewQuestionItem(BaseModel):
    id: int = Field(default=0, description="1-based position of this question in the set.")
    category: str = Field(max_length=80)
    question: str = Field(min_length=1, max_length=1200)
    purpose: str = Field(default="", max_length=700)
    sample_answer: str = Field(default="", max_length=1600)
    strong_answer_signals: list[str] = Field(default_factory=list, max_length=6)
    follow_up_questions: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("category", "question", "purpose", "sample_answer", mode="before")
    @classmethod
    def clean_text(cls, value):
        return str(value or "").strip()

    @field_validator("strong_answer_signals", "follow_up_questions", mode="before")
    @classmethod
    def clean_list(cls, value):
        if not isinstance(value, list):
            return []
        cleaned = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                cleaned.append(text[:300])
        return cleaned


class EmployerInterviewQuestionsPayload(BaseModel):
    questions: list[EmployerInterviewQuestionItem] = Field(default_factory=list)


class EmployerInterviewQuestionsRequest(BaseModel):
    interview_round: EmployerInterviewRound = EmployerInterviewRound.TECHNICAL
    focus_areas: list[str] = Field(default_factory=list, max_length=8)
    include_follow_ups: bool = True

    @field_validator("focus_areas", mode="before")
    @classmethod
    def clean_focus_areas(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        cleaned = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                cleaned.append(text[:80])
        return cleaned

    @model_validator(mode="after")
    def validate_size(self):
        if len(self.model_dump_json(exclude_none=True)) > 2000:
            raise ValueError("AI interview question input is too large")
        return self


class EmployerInterviewQuestionsResponse(BaseModel):
    job_id: str
    candidate_id: str
    job_title: str
    company_name: Optional[str] = None
    interview_round: EmployerInterviewRound
    questions: list[EmployerInterviewQuestionItem] = Field(default_factory=list)
