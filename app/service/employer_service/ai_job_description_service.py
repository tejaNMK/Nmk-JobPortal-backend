from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.employer_model.ai_job_description_usage import AIJobDescriptionUsage
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.schema.employer_ai_job_description import (
    AI_JOB_DESCRIPTION_FEATURE_KEY,
    AI_JOB_DESCRIPTION_MONTHLY_LIMIT_KEY,
    AIJobDescriptionGenerateRequest,
    AIJobDescriptionImproveRequest,
    AIJobDescriptionRegenerateRequest,
    AIJobDescriptionResponse,
    AIJobDescriptionSectionItemsPayload,
    AIJobDescriptionSectionResponse,
    AIJobDescriptionSectionTextPayload,
    AIJobDescriptionStructuredPayload,
    AIUsageSchema,
)
from app.service.employer_service.ai_service import (
    AIService,
    AIServiceError,
    DEFAULT_BEDROCK_MODEL_ID,
    ai_error_status_code,
)
from app.service.employer_service.ai_providers import (
    AIProviderRequest,
    create_employer_ai_provider,
)
from app.service.subscription.subscription_validator import SubscriptionValidator


logger = logging.getLogger(__name__)
AI_JOB_DESCRIPTION_PROMPT_VERSION = "ai_job_description_v2"
PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts" / "job_description"
REQUIRED_OUTPUT_KEYS = {
    "title": "",
    "companyOverview": "",
    "roleSummary": "",
    "responsibilities": [],
    "requiredSkills": [],
    "preferredSkills": [],
    "requiredQualifications": [],
    "preferredQualifications": [],
    "technicalSkills": [],
    "softSkills": [],
    "benefits": [],
    "perks": [],
    "workEnvironment": "",
    "careerGrowth": "",
    "salaryInformation": "",
    "equalOpportunityStatement": "",
    "applicationProcess": "",
    "keywords": [],
    "atsOptimizedSummary": "",
    "atsScore": 90,
    "markdown": "",
    "html": "",
}
SECTION_ALIASES = {
    "responsibilities": "responsibilities",
    "responsibility": "responsibilities",
    "key responsibilities": "responsibilities",
    "requirements": "requirements",
    "requirement": "requirements",
    "qualifications": "requirements",
    "qualification": "requirements",
    "required qualifications": "requirements",
    "required requirements": "requirements",
    "benefits": "benefits",
    "benefit": "benefits",
    "perks and benefits": "benefits",
    "application instructions": "application_instructions",
    "application instruction": "application_instructions",
    "application_instructions": "application_instructions",
    "how to apply": "application_instructions",
    "application process": "application_instructions",
}
LIST_SECTIONS = {"responsibilities", "requirements", "benefits"}
SECTION_LABELS = {
    "responsibilities": "responsibilities",
    "requirements": "requirements",
    "benefits": "benefits",
    "application_instructions": "application instructions",
}
UNRELATED_SECTION_PATTERNS = {
    "responsibilities": (
        "requirements",
        "required qualifications",
        "benefits",
        "application instructions",
        "application process",
        "ats optimized summary",
        "job summary",
        "company overview",
    ),
    "requirements": (
        "responsibilities",
        "key responsibilities",
        "benefits",
        "application instructions",
        "application process",
        "ats optimized summary",
        "job summary",
        "company overview",
    ),
    "benefits": (
        "responsibilities",
        "key responsibilities",
        "requirements",
        "required qualifications",
        "application instructions",
        "application process",
        "ats optimized summary",
        "job summary",
        "company overview",
    ),
    "application_instructions": (
        "responsibilities",
        "key responsibilities",
        "requirements",
        "required qualifications",
        "benefits",
        "salary information",
        "ats optimized summary",
        "job summary",
        "company overview",
    ),
}


@dataclass
class AIProviderResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    parsed_payload: Any = None
    model_id: str | None = None
    provider: str | None = None
    latency_ms: int = 0
    repaired: bool = False
    repair_attempts: int = 0
    prompt_version: str | None = None
    cost_estimate_usd: float = 0.0


@dataclass
class AIJobDescriptionProviderConfig:
    model: str
    max_output_chars: int
    max_tokens: int
    rate_limit_per_minute: int
    provider: str = "bedrock"
    api_key: str | None = None
    api_url: str | None = None
    timeout_seconds: float | None = None
    retry_attempts: int = 3
    cache_ttl_seconds: int = 86400


class _MemoryTTLCache:
    _items: dict[str, tuple[float, AIJobDescriptionResponse]] = {}

    @classmethod
    def get(cls, key: str) -> AIJobDescriptionResponse | None:
        item = cls._items.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            cls._items.pop(key, None)
            return None
        return value

    @classmethod
    def set(cls, key: str, value: AIJobDescriptionResponse, ttl_seconds: int) -> None:
        cls._items[key] = (time.monotonic() + ttl_seconds, value)


class AIJobDescriptionService:
    _rate_limit_window_seconds = 60
    _rate_limit_hits: dict[str, list[float]] = {}

    @staticmethod
    def _positive_int(value: str | None, env_name: str) -> int:
        if value is None or not str(value).strip():
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} is required for AI job description generation.",
            )
        try:
            parsed = int(str(value).strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} must be a positive integer.",
            ) from exc
        if parsed <= 0:
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} must be a positive integer.",
            )
        return parsed

    @staticmethod
    def _positive_float(value: str | None, env_name: str) -> float:
        if value is None or not str(value).strip():
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} is required for AI job description generation.",
            )
        try:
            parsed = float(str(value).strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} must be a positive number.",
            ) from exc
        if parsed <= 0:
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} must be a positive number.",
            )
        return parsed

    @staticmethod
    def _required_text(value: str | None, env_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise HTTPException(
                status_code=503,
                detail=f"{env_name} is required for AI job description generation.",
            )
        return text

    @staticmethod
    def _env_with_fallback(name: str, default: str | None = None, *, prefix: str | None = None) -> str | None:
        if prefix:
            value = os.getenv(f"EMPLOYER_{prefix}_{name}")
            if value is not None:
                return value
            value = os.getenv(f"{prefix}_{name}")
            if value is not None:
                return value
        value = os.getenv(f"EMPLOYER_BEDROCK_{name}")
        if value is not None:
            return value
        return os.getenv(f"BEDROCK_{name}", default)

    @staticmethod
    def _env_label(name: str, *, prefix: str | None = None) -> str:
        if prefix and os.getenv(f"EMPLOYER_{prefix}_{name}") is not None:
            return f"EMPLOYER_{prefix}_{name}"
        if prefix and os.getenv(f"{prefix}_{name}") is not None:
            return f"{prefix}_{name}"
        if os.getenv(f"EMPLOYER_BEDROCK_{name}") is not None:
            return f"EMPLOYER_BEDROCK_{name}"
        return f"BEDROCK_{name}"

    @staticmethod
    def _provider_model(
        *,
        provider: str,
        provider_default: str,
        prefix: str | None,
    ) -> str:
        for name in (
            f"EMPLOYER_{prefix}_MODEL_ID" if prefix else None,
            f"{prefix}_MODEL_ID" if prefix else None,
            "EMPLOYER_AI_MODEL",
            "AI_MODEL",
        ):
            if not name:
                continue
            value = os.getenv(name)
            if value and value.strip():
                return value.strip()

        normalized = provider.strip().lower().replace("-", "_")
        if normalized in {"bedrock", "aws_bedrock"}:
            return AIJobDescriptionService._env_with_fallback(
                "MODEL_ID",
                provider_default,
                prefix=prefix,
            )
        return provider_default

    @staticmethod
    def _provider_config(prefix: str | None = "AI_JOB_DESCRIPTION_BEDROCK") -> AIJobDescriptionProviderConfig:
        provider = (
            os.getenv("EMPLOYER_AI_PROVIDER")
            or os.getenv("EMPLOYER_AI_JOB_DESCRIPTION_PROVIDER")
            or os.getenv("AI_JOB_DESCRIPTION_PROVIDER")
            or os.getenv("AI_PROVIDER")
            or "bedrock"
        )
        model_default = {
            "openai": os.getenv("EMPLOYER_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini")),
            "azure_openai": os.getenv(
                "EMPLOYER_AZURE_OPENAI_MODEL",
                os.getenv("AZURE_OPENAI_MODEL", "gpt-4.1"),
            ),
            "azure": os.getenv(
                "EMPLOYER_AZURE_OPENAI_MODEL",
                os.getenv("AZURE_OPENAI_MODEL", "gpt-4.1"),
            ),
            "anthropic": os.getenv(
                "EMPLOYER_ANTHROPIC_MODEL",
                os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            ),
            "claude": os.getenv(
                "EMPLOYER_ANTHROPIC_MODEL",
                os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            ),
            "gemini": os.getenv("EMPLOYER_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-pro")),
            "google": os.getenv("EMPLOYER_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-pro")),
            "deepseek": os.getenv("EMPLOYER_DEEPSEEK_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
        }.get(provider.strip().lower(), DEFAULT_BEDROCK_MODEL_ID)
        return AIJobDescriptionProviderConfig(
            provider=provider,
            model=AIJobDescriptionService._provider_model(
                provider=provider,
                provider_default=model_default,
                prefix=prefix,
            ),
            max_output_chars=AIJobDescriptionService._positive_int(
                AIJobDescriptionService._env_with_fallback(
                    "MAX_OUTPUT_CHARS",
                    "12000",
                    prefix=prefix,
                ),
                AIJobDescriptionService._env_label("MAX_OUTPUT_CHARS", prefix=prefix),
            ),
            max_tokens=AIJobDescriptionService._positive_int(
                AIJobDescriptionService._env_with_fallback(
                    "MAX_TOKENS",
                    "4000",
                    prefix=prefix,
                ),
                AIJobDescriptionService._env_label("MAX_TOKENS", prefix=prefix),
            ),
            rate_limit_per_minute=AIJobDescriptionService._positive_int(
                AIJobDescriptionService._env_with_fallback(
                    "RATE_LIMIT_PER_MINUTE",
                    "10",
                    prefix=prefix,
                ),
                AIJobDescriptionService._env_label("RATE_LIMIT_PER_MINUTE", prefix=prefix),
            ),
            timeout_seconds=AIJobDescriptionService._positive_float(
                AIJobDescriptionService._env_with_fallback(
                    "TIMEOUT_SECONDS",
                    os.getenv("AI_TIMEOUT_SECONDS", "30"),
                    prefix=prefix,
                ),
                AIJobDescriptionService._env_label("TIMEOUT_SECONDS", prefix=prefix),
            ),
            retry_attempts=AIJobDescriptionService._positive_int(
                os.getenv("AI_RETRY_ATTEMPTS", "3"),
                "AI_RETRY_ATTEMPTS",
            ),
            cache_ttl_seconds=AIJobDescriptionService._positive_int(
                os.getenv("AI_JOB_DESCRIPTION_CACHE_TTL_SECONDS", "86400"),
                "AI_JOB_DESCRIPTION_CACHE_TTL_SECONDS",
            ),
        )

    @staticmethod
    def _check_rate_limit(user_id: UUID, config: AIJobDescriptionProviderConfig) -> None:
        now = time.monotonic()
        cutoff = now - AIJobDescriptionService._rate_limit_window_seconds
        key = str(user_id)
        hits = [
            hit
            for hit in AIJobDescriptionService._rate_limit_hits.get(key, [])
            if hit >= cutoff
        ]
        if len(hits) >= config.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Too many AI job description requests. Please try again shortly.",
            )
        hits.append(now)
        AIJobDescriptionService._rate_limit_hits[key] = hits

    @staticmethod
    def _render_list(label: str, values: list[str] | None) -> str:
        if not values:
            return f"{label}: Infer from the available role context"
        return f"{label}:\n" + "\n".join(f"- {value}" for value in values)

    @staticmethod
    def _load_prompt_template(name: str) -> str:
        path = PROMPT_DIR / f"{name}.txt"
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.exception("AI job description prompt template could not be loaded: %s", path)
            raise HTTPException(status_code=503, detail="AI prompt template is unavailable.") from exc

    @staticmethod
    def _schema_instruction() -> str:
        keys = json.dumps(REQUIRED_OUTPUT_KEYS, indent=2)
        return (
            "Return a JSON object with exactly these keys and compatible value types. "
            "Arrays must contain polished bullet strings. atsScore must be 0-100. "
            "Set markdown and html to empty strings; the application builds those representations. "
            "Keep the complete editable description concise, approximately 350-500 words total, "
            "and keep generated content below 5,000 characters to avoid truncated JSON.\n"
            f"{keys}"
        )

    @staticmethod
    def _section_error(
        status_code: int,
        *,
        section: str | None,
        message: str | None = None,
        code: str,
    ) -> HTTPException:
        label = SECTION_LABELS.get(section or "", section or "section")
        return HTTPException(
            status_code=status_code,
            detail={
                "message": message or f"AI did not return valid {label} content",
                "code": code,
            },
        )

    @staticmethod
    def _canonical_section(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[_\-]+", " ", str(value).strip().lower())
        normalized = re.sub(r"\s+", " ", normalized)
        section = SECTION_ALIASES.get(normalized)
        if not section:
            raise AIJobDescriptionService._section_error(
                422,
                section=None,
                message="Unsupported job-description section",
                code="INVALID_AI_SECTION",
            )
        return section

    @staticmethod
    def _section_schema_instruction(section: str) -> str:
        if section == "application_instructions":
            return (
                'Return exactly one JSON object with this schema: {"text": "one concise paragraph"}. '
                "The paragraph must be under 2,000 characters, contain no headings or bullets, and must not include "
                "ATS summaries, responsibilities, requirements, benefits, salary information, URLs, email addresses, "
                "phone numbers, deadlines, or company policies unless they were supplied by the employer."
            )
        max_chars = 80 if section == "benefits" else 300
        return (
            'Return exactly one JSON object with this schema: {"items": ["item 1", "item 2", "item 3"]}. '
            f"Provide 3-20 unique {SECTION_LABELS[section]} items. Each item must be no more than {max_chars} "
            "characters. Do not include headings, markdown, numbering, commentary, or unrelated job-description sections."
        )

    @staticmethod
    def _section_generation_prompt(request: AIJobDescriptionGenerateRequest, section: str) -> str:
        fields = [
            f"Requested section: {section}",
            f"Job title: {request.job_title}",
            f"Company name: {request.company_name or 'Not provided'}",
            f"Company description: {request.company_description or 'Not provided'}",
            f"Department: {request.department or 'Not provided'}",
            f"Industry: {request.industry or 'Not provided'}",
            f"Employment type: {request.employment_type or 'Not provided'}",
            f"Workplace type: {request.workplace_type or 'Not provided'}",
            f"Location: {request.location or 'Not provided'}",
            f"Education: {request.education or 'Not provided'}",
            f"Experience text: {request.experience or 'Not provided'}",
            (
                "Experience: "
                f"{request.minimum_experience if request.minimum_experience is not None else 'Not provided'}"
                " to "
                f"{request.maximum_experience if request.maximum_experience is not None else 'Not provided'} years"
            ),
            f"Salary: {request.salary or 'Not provided'}",
            AIJobDescriptionService._render_list("Skills", request.skills),
            AIJobDescriptionService._render_list("Required skills", request.required_skills),
            AIJobDescriptionService._render_list("Preferred skills", request.preferred_skills),
            AIJobDescriptionService._render_list("Qualifications", request.qualifications),
            AIJobDescriptionService._render_list("Required qualifications", request.required_qualifications),
            AIJobDescriptionService._render_list("Preferred qualifications", request.preferred_qualifications),
            AIJobDescriptionService._render_list("Existing responsibilities", request.responsibilities),
            AIJobDescriptionService._render_list("Existing benefits", request.benefits),
            f"Tone: {request.tone or 'professional'}",
            f"Output language: {request.output_language or 'English'}",
            f"Additional instructions: {request.additional_instructions or 'Not provided'}",
            "Generate only the requested section. Reject all unrelated sections.",
            AIJobDescriptionService._section_schema_instruction(section),
        ]
        return "\n\n".join(fields)

    @staticmethod
    def _section_rewrite_prompt(
        *,
        section: str,
        existing_description: str,
        instructions: str | None,
        tone: str | None,
    ) -> str:
        return "\n\n".join(
            [
                f"Requested section: {section}",
                f"Tone: {tone or 'professional'}",
                f"Instructions: {instructions or 'Rewrite the requested section clearly while preserving job facts.'}",
                f"Existing content/context:\n{existing_description}",
                "Rewrite only the requested section. Do not return any other job-description section.",
                AIJobDescriptionService._section_schema_instruction(section),
            ]
        )

    @staticmethod
    def _repair_section_prompt(
        *,
        section: str,
        original_prompt: str,
        invalid_response: str,
        validation_error: str,
    ) -> str:
        return "\n\n".join(
            [
                "The previous AI response was invalid for section-only job-description generation.",
                f"Requested section: {section}",
                AIJobDescriptionService._section_schema_instruction(section),
                "Reject unrelated sections and return only valid JSON for the requested section.",
                "Original request:",
                original_prompt,
                "Invalid response:",
                invalid_response[:2000],
                "Validation error:",
                validation_error[:1000],
            ]
        )

    @staticmethod
    def _generation_prompt(request: AIJobDescriptionGenerateRequest) -> str:
        fields = [
            f"Job title: {request.job_title}",
            f"Company name: {request.company_name or 'Infer from context'}",
            f"Company description: {request.company_description or 'Write a general company overview without inventing facts'}",
            f"Department: {request.department or 'Not provided'}",
            f"Industry: {request.industry or 'Not provided'}",
            f"Employment type: {request.employment_type or 'Not provided'}",
            f"Workplace type: {request.workplace_type or 'Not provided'}",
            f"Location: {request.location or 'Not provided'}",
            f"Education: {request.education or 'Infer reasonable education requirements'}",
            f"Experience text: {request.experience or 'Infer from numeric range if available'}",
            (
                "Experience: "
                f"{request.minimum_experience if request.minimum_experience is not None else 'Not provided'}"
                " to "
                f"{request.maximum_experience if request.maximum_experience is not None else 'Not provided'} years"
            ),
            f"Salary: {request.salary or 'Use a transparent, non-numeric statement unless salary is provided'}",
            AIJobDescriptionService._render_list("Skills", request.skills),
            AIJobDescriptionService._render_list("Required skills", request.required_skills),
            AIJobDescriptionService._render_list("Preferred skills", request.preferred_skills),
            AIJobDescriptionService._render_list("Qualifications", request.qualifications),
            AIJobDescriptionService._render_list("Required qualifications", request.required_qualifications),
            AIJobDescriptionService._render_list("Preferred qualifications", request.preferred_qualifications),
            AIJobDescriptionService._render_list("Key responsibilities", request.responsibilities),
            AIJobDescriptionService._render_list("Benefits", request.benefits),
            f"Visa sponsorship: {request.visa_sponsorship or 'Use compliant, neutral language'}",
            f"Shift: {request.shift or 'Infer standard business hours if appropriate'}",
            AIJobDescriptionService._render_list("Languages", request.languages),
            f"Job category: {request.job_category or 'Infer'}",
            AIJobDescriptionService._render_list("Keywords", request.keywords),
            f"Tone: {request.tone or 'professional'}",
            f"Output language: {request.output_language or 'English'}",
            f"Additional instructions: {request.additional_instructions or 'Not provided'}",
            AIJobDescriptionService._schema_instruction(),
        ]
        return "\n\n".join(fields)

    @staticmethod
    def _improvement_prompt(request: AIJobDescriptionImproveRequest) -> str:
        parts = [
            "Improve this existing job description while preserving every factual requirement.",
            f"Existing description:\n{request.existing_description}",
            f"Tone: {request.tone or 'professional'}",
            f"Length: {request.length or '1000-1500 words'}",
            f"Industry: {request.industry or 'Infer from description'}",
            AIJobDescriptionService._schema_instruction(),
        ]
        if request.additional_instructions:
            parts.append(f"Additional instructions:\n{request.additional_instructions}")
        return "\n\n".join(parts)

    @staticmethod
    def _regeneration_prompt(request: AIJobDescriptionRegenerateRequest) -> str:
        return "\n\n".join(
            [
                f"Requested section: {request.section}",
                f"Tone: {request.tone or 'professional'}",
                f"Instructions: {request.instructions or 'Improve the section while preserving job facts.'}",
                f"Existing job description:\n{request.existing_description}",
                (
                    "Return the full structured job description JSON with only the requested section "
                    "changed. Preserve all other available content."
                ),
                AIJobDescriptionService._schema_instruction(),
            ]
        )

    @staticmethod
    def _system_prompt(operation: str) -> str:
        return AIJobDescriptionService._load_prompt_template(operation)

    @staticmethod
    async def _call_ai_provider(
        user_prompt: str,
        *,
        operation: str,
        config: AIJobDescriptionProviderConfig,
    ) -> AIProviderResult:
        last_error: AIServiceError | None = None
        try:
            provider = create_employer_ai_provider(
                config.provider,
                model_id=config.model,
                timeout_seconds=config.timeout_seconds or 30,
            )
        except AIServiceError as exc:
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail=str(exc),
            ) from exc
        attempts = max(config.retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                result = await provider.generate_json(
                    AIProviderRequest(
                        system_prompt=AIJobDescriptionService._system_prompt(operation),
                        user_prompt=user_prompt,
                        max_tokens=config.max_tokens,
                        temperature=0.35,
                        feature=AI_JOB_DESCRIPTION_FEATURE_KEY,
                        prompt_version=f"{AI_JOB_DESCRIPTION_PROMPT_VERSION}_{operation}",
                        response_model=AIJobDescriptionStructuredPayload,
                    )
                )
                cost = AIJobDescriptionService._estimate_cost(
                    provider=result.provider,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                logger.info(
                    "AI job description invocation succeeded.",
                    extra={
                        "event": "ai_job_description_succeeded",
                        "provider": result.provider,
                        "model": result.model_id,
                        "operation": operation,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "latency_ms": result.latency_ms,
                        "cost_estimate_usd": cost,
                        "retry_attempt": attempt,
                        "repair_attempts": result.repair_attempts,
                    },
                )
                return AIProviderResult(
                    content=result.content,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    parsed_payload=result.data,
                    model_id=result.model_id,
                    provider=result.provider,
                    latency_ms=result.latency_ms,
                    repaired=result.repaired,
                    repair_attempts=result.repair_attempts,
                    prompt_version=f"{AI_JOB_DESCRIPTION_PROMPT_VERSION}_{operation}",
                    cost_estimate_usd=cost,
                )
            except AIServiceError as exc:
                last_error = exc
                retryable = exc.category in {"PROVIDER_UNAVAILABLE", "PROVIDER_REJECTED"}
                logger.warning(
                    "AI job description provider request failed.",
                    extra={
                        "event": "ai_job_description_failed",
                        "operation": operation,
                        "provider": config.provider,
                        "model": config.model,
                        "retry_attempt": attempt,
                        "retryable": retryable,
                        "error_category": exc.category,
                    },
                )
                if not retryable or attempt >= attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8) * 0.25)

        if last_error is None:
            last_error = AIServiceError("AI provider failed.", category="PROVIDER_UNAVAILABLE")
        raise HTTPException(
            status_code=ai_error_status_code(last_error),
            detail="AI provider failed to generate a description.",
        ) from last_error

    @staticmethod
    async def _call_section_ai_provider(
        user_prompt: str,
        *,
        section: str,
        operation: str,
        config: AIJobDescriptionProviderConfig,
    ) -> AIProviderResult:
        try:
            provider = create_employer_ai_provider(
                config.provider,
                model_id=config.model,
                timeout_seconds=config.timeout_seconds or 30,
            )
        except AIServiceError as exc:
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail=str(exc),
            ) from exc

        prompt_version = f"{AI_JOB_DESCRIPTION_PROMPT_VERSION}_{operation}_{section}"
        response_model = (
            AIJobDescriptionSectionTextPayload
            if section == "application_instructions"
            else AIJobDescriptionSectionItemsPayload
        )
        first_result: Any = None
        first_error: Exception | None = None
        for attempt in (0, 1):
            prompt = user_prompt
            temperature = 0.25
            if attempt == 1:
                prompt = AIJobDescriptionService._repair_section_prompt(
                    section=section,
                    original_prompt=user_prompt,
                    invalid_response=getattr(first_result, "content", ""),
                    validation_error=str(first_error or "Invalid section response"),
                )
                temperature = 0
            try:
                result = await provider.generate_json(
                    AIProviderRequest(
                        system_prompt=AIJobDescriptionService._system_prompt(operation),
                        user_prompt=prompt,
                        max_tokens=min(config.max_tokens, 1200),
                        temperature=temperature,
                        feature=AI_JOB_DESCRIPTION_FEATURE_KEY,
                        prompt_version=prompt_version,
                        response_model=response_model,
                    )
                )
                provider_result = AIProviderResult(
                    content=result.content,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    parsed_payload=result.data,
                    model_id=result.model_id,
                    provider=result.provider,
                    latency_ms=result.latency_ms,
                    repaired=result.repaired or attempt == 1,
                    repair_attempts=result.repair_attempts + attempt,
                    prompt_version=prompt_version,
                    cost_estimate_usd=AIJobDescriptionService._estimate_cost(
                        provider=result.provider,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                    ),
                )
                AIJobDescriptionService._response_from_section_result(provider_result, section=section)
                return provider_result
            except AIServiceError as exc:
                if exc.category in {"PROVIDER_UNAVAILABLE", "PROVIDER_REJECTED"}:
                    raise HTTPException(
                        status_code=ai_error_status_code(exc),
                        detail="AI provider failed to generate a description.",
                    ) from exc
                first_error = exc
            except (HTTPException, ValidationError, ValueError, TypeError) as exc:
                first_error = exc
            first_result = locals().get("result")

        raise AIJobDescriptionService._section_error(
            502,
            section=section,
            code="INVALID_AI_SECTION_RESPONSE",
        )

    @staticmethod
    def _strip_markdown_noise(text: str) -> str:
        cleaned = str(text or "").replace("\x00", "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", cleaned)
        cleaned = re.sub(
            r"^\s*(?:responsibilities|key responsibilities|requirements|required qualifications|"
            r"benefits|perks and benefits|application instructions|application process|"
            r"ats optimized summary|job summary|company overview)\s*:\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if re.fullmatch(
            r"(?:responsibilities|key responsibilities|requirements|required qualifications|"
            r"benefits|perks and benefits|application instructions|application process|"
            r"ats optimized summary|job summary|company overview)",
            cleaned,
            flags=re.IGNORECASE,
        ):
            return ""
        return cleaned

    @staticmethod
    def _has_unrelated_section(text: str, section: str) -> bool:
        lowered = text.lower()
        for phrase in UNRELATED_SECTION_PATTERNS[section]:
            if phrase in {"ats optimized summary", "job summary", "company overview"} and phrase in lowered:
                return True
            if re.search(rf"(?:^|\n|\b#*\s*){re.escape(phrase)}\s*:", lowered):
                return True
            if re.search(rf"(?:^|\n)\s*#+\s*{re.escape(phrase)}\b", lowered):
                return True
        return False

    @staticmethod
    def _trim_at_sentence_boundary(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        clipped = text[:limit].rsplit(" ", 1)[0].strip()
        sentence_end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        if sentence_end >= max(40, limit // 2):
            return clipped[: sentence_end + 1].strip()
        return clipped.rstrip(" ,;:")

    @staticmethod
    def _clean_section_items(items: list[Any], section: str) -> list[str]:
        limit = 80 if section == "benefits" else 300
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in items:
            if AIJobDescriptionService._has_unrelated_section(str(raw), section):
                raise AIJobDescriptionService._section_error(
                    502,
                    section=section,
                    code="INVALID_AI_SECTION_RESPONSE",
                )
            item = AIJobDescriptionService._strip_markdown_noise(str(raw))
            if not item:
                continue
            if AIJobDescriptionService._has_unrelated_section(item, section):
                raise AIJobDescriptionService._section_error(
                    502,
                    section=section,
                    code="INVALID_AI_SECTION_RESPONSE",
                )
            item = AIJobDescriptionService._trim_at_sentence_boundary(item, limit)
            key = item.casefold()
            if item and key not in seen:
                cleaned.append(item)
                seen.add(key)
            if len(cleaned) >= 20:
                break
        if len(cleaned) < 3:
            raise AIJobDescriptionService._section_error(
                502,
                section=section,
                code="INVALID_AI_SECTION_RESPONSE",
            )
        return cleaned

    @staticmethod
    def _clean_section_paragraph(text: str, section: str) -> str:
        if AIJobDescriptionService._has_unrelated_section(text, section):
            raise AIJobDescriptionService._section_error(
                502,
                section=section,
                code="INVALID_AI_SECTION_RESPONSE",
            )
        lines = [
            AIJobDescriptionService._strip_markdown_noise(line)
            for line in str(text or "").splitlines()
        ]
        paragraph = " ".join(line for line in lines if line)
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            raise AIJobDescriptionService._section_error(
                502,
                section=section,
                code="INVALID_AI_SECTION_RESPONSE",
            )
        if re.search(r"ats optimized summary", paragraph, flags=re.IGNORECASE):
            raise AIJobDescriptionService._section_error(
                502,
                section=section,
                code="INVALID_AI_SECTION_RESPONSE",
            )
        return AIJobDescriptionService._trim_at_sentence_boundary(paragraph, 2000)

    @staticmethod
    def _response_from_section_result(
        result: AIProviderResult,
        *,
        section: str,
    ) -> AIJobDescriptionSectionResponse:
        data = result.parsed_payload
        if data is None and result.content:
            try:
                data = json.loads(AIJobDescriptionService._strip_markdown_noise(result.content))
            except json.JSONDecodeError as exc:
                raise AIJobDescriptionService._section_error(
                    502,
                    section=section,
                    code="INVALID_AI_SECTION_RESPONSE",
                ) from exc
        if not isinstance(data, dict):
            raise AIJobDescriptionService._section_error(
                502,
                section=section,
                code="INVALID_AI_SECTION_RESPONSE",
            )
        if section in LIST_SECTIONS:
            try:
                model = AIJobDescriptionSectionItemsPayload.model_validate(data)
            except ValidationError as exc:
                raise AIJobDescriptionService._section_error(
                    502,
                    section=section,
                    code="INVALID_AI_SECTION_RESPONSE",
                ) from exc
            content: list[str] | str = AIJobDescriptionService._clean_section_items(model.items, section)
            generated_description = "\n".join(content)
        else:
            try:
                model = AIJobDescriptionSectionTextPayload.model_validate(data)
            except ValidationError as exc:
                raise AIJobDescriptionService._section_error(
                    502,
                    section=section,
                    code="INVALID_AI_SECTION_RESPONSE",
                ) from exc
            content = AIJobDescriptionService._clean_section_paragraph(model.text, section)
            generated_description = content
        return AIJobDescriptionSectionResponse(
            section=section,
            content=content,
            generated_description=generated_description,
            usage=AIUsageSchema(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                provider=result.provider,
                model=result.model_id,
                latency_ms=result.latency_ms,
                cost_estimate_usd=result.cost_estimate_usd,
            ),
        )

    @staticmethod
    def _validate_ai_result(
        result: AIProviderResult,
        config: AIJobDescriptionProviderConfig,
    ) -> None:
        if not result.content and not result.parsed_payload:
            raise HTTPException(
                status_code=502,
                detail="AI provider returned an empty description.",
            )
        if len(result.content) > config.max_output_chars:
            raise HTTPException(
                status_code=502,
                detail="AI provider returned a description that is too long.",
            )

    @staticmethod
    def _estimate_cost(*, provider: str, input_tokens: int, output_tokens: int) -> float:
        input_per_million = float(os.getenv("AI_COST_INPUT_PER_MILLION_USD", "0") or 0)
        output_per_million = float(os.getenv("AI_COST_OUTPUT_PER_MILLION_USD", "0") or 0)
        return round(
            (input_tokens * input_per_million + output_tokens * output_per_million) / 1_000_000,
            6,
        )

    @staticmethod
    async def _enforce_subscription(session: AsyncSession, user_id: UUID) -> SubscriptionValidator:
        validator = SubscriptionValidator(session=session, user_id=user_id, role="EMPLOYER")
        await validator.require_feature(AI_JOB_DESCRIPTION_FEATURE_KEY)
        await validator.ensure_limit_available(
            AI_JOB_DESCRIPTION_MONTHLY_LIMIT_KEY,
            period="month",
        )
        return validator

    @staticmethod
    async def _validate_job_ownership(
        session: AsyncSession,
        *,
        employer: EmployerProfile,
        job_id: str | None,
    ) -> None:
        if not job_id:
            return
        result = await session.execute(
            select(Job.job_id).where(
                Job.job_id == job_id,
                Job.employer_id == str(employer.id),
                Job.is_deleted.is_(False),
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Job not found")

    @staticmethod
    async def _record_success(
        session: AsyncSession,
        *,
        validator: SubscriptionValidator,
        employer: EmployerProfile,
        user_id: UUID,
        operation_type: str,
        job_id: str | None,
        result: AIProviderResult,
        config: AIJobDescriptionProviderConfig,
    ) -> None:
        user_subscription = await validator.validate_active_subscription()
        period_start, period_end = SubscriptionValidator._period_window("month")
        session.add(
            AIJobDescriptionUsage(
                employer_user_id=user_id,
                company_id=str(employer.id),
                operation_type=operation_type,
                job_id=job_id,
                ai_model=config.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                request_status="SUCCESS",
            )
        )
        await UserSubscriptionRepository.increment_usage(
            session=session,
            user_subscription_id=user_subscription.user_subscription_id,
            user_id=user_id,
            feature_name=AI_JOB_DESCRIPTION_MONTHLY_LIMIT_KEY,
            amount=1,
            period_start=period_start,
            period_end=period_end,
            commit=False,
        )
        await commit_rollback(session)

    @staticmethod
    def _cache_key(operation: str, request: Any, config: AIJobDescriptionProviderConfig) -> str:
        body = {
            "operation": operation,
            "provider": config.provider,
            "model": config.model,
            "prompt_version": f"{AI_JOB_DESCRIPTION_PROMPT_VERSION}_{operation}",
            "request": request.model_dump(mode="json", exclude_none=True),
        }
        encoded = json.dumps(body, sort_keys=True, ensure_ascii=False)
        return "ai:job-description:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    async def _cache_get(key: str) -> AIJobDescriptionResponse | None:
        url = os.getenv("AI_JOB_DESCRIPTION_CACHE_URL") or os.getenv("RATE_LIMIT_STORAGE_URL", "")
        if url.lower().startswith(("redis://", "rediss://")):
            try:
                import redis.asyncio as redis

                client = redis.from_url(url, decode_responses=True)
                cached = await client.get(key)
                await client.aclose()
                if cached:
                    return AIJobDescriptionResponse.model_validate_json(cached)
            except Exception:
                logger.warning("AI job description Redis cache read failed.", exc_info=True)
        return _MemoryTTLCache.get(key)

    @staticmethod
    async def _cache_set(
        key: str,
        value: AIJobDescriptionResponse,
        ttl_seconds: int,
    ) -> None:
        url = os.getenv("AI_JOB_DESCRIPTION_CACHE_URL") or os.getenv("RATE_LIMIT_STORAGE_URL", "")
        if url.lower().startswith(("redis://", "rediss://")):
            try:
                import redis.asyncio as redis

                client = redis.from_url(url, decode_responses=True)
                await client.setex(key, ttl_seconds, value.model_dump_json())
                await client.aclose()
                return
            except Exception:
                logger.warning("AI job description Redis cache write failed.", exc_info=True)
        _MemoryTTLCache.set(key, value, ttl_seconds)

    @staticmethod
    def _normalize_payload(data: dict[str, Any] | None, *, fallback_title: str = "") -> AIJobDescriptionStructuredPayload:
        normalized = dict(REQUIRED_OUTPUT_KEYS)
        if data:
            normalized.update({key: value for key, value in data.items() if key in normalized})
        normalized["title"] = str(normalized.get("title") or fallback_title or "Professional Role").strip()
        list_keys = [
            "responsibilities",
            "requiredSkills",
            "preferredSkills",
            "requiredQualifications",
            "preferredQualifications",
            "technicalSkills",
            "softSkills",
            "benefits",
            "perks",
            "keywords",
        ]
        for key in list_keys:
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = [item.strip(" -") for item in value.splitlines() if item.strip(" -")]
            elif not isinstance(value, list):
                normalized[key] = []
            normalized[key] = [str(item).strip() for item in normalized[key] if str(item).strip()]

        normalized["atsScore"] = _coerce_ats_score(normalized.get("atsScore"))
        payload = AIJobDescriptionStructuredPayload.model_validate(normalized)
        if not payload.markdown:
            payload.markdown = AIJobDescriptionService._build_markdown(payload)
        if not payload.html:
            payload.html = AIJobDescriptionService._markdown_to_basic_html(payload.markdown)
        return payload

    @staticmethod
    def _build_markdown(payload: AIJobDescriptionStructuredPayload) -> str:
        sections: list[str] = [f"# {payload.title}"]
        text_sections = [
            ("Company Overview", payload.companyOverview),
            ("Role Summary", payload.roleSummary),
            ("Work Environment", payload.workEnvironment),
            ("Career Growth", payload.careerGrowth),
            ("Salary Information", payload.salaryInformation),
            ("Equal Opportunity Statement", payload.equalOpportunityStatement),
            ("Application Process", payload.applicationProcess),
            ("ATS Optimized Summary", payload.atsOptimizedSummary),
        ]
        list_sections = [
            ("Key Responsibilities", payload.responsibilities),
            ("Required Skills", payload.requiredSkills),
            ("Preferred Skills", payload.preferredSkills),
            ("Required Qualifications", payload.requiredQualifications),
            ("Preferred Qualifications", payload.preferredQualifications),
            ("Technical Skills", payload.technicalSkills),
            ("Soft Skills", payload.softSkills),
            ("Benefits", payload.benefits),
            ("Perks", payload.perks),
            ("Keywords", payload.keywords),
        ]
        for heading, text in text_sections:
            if text:
                sections.append(f"## {heading}\n{text}")
        for heading, items in list_sections:
            if items:
                sections.append(f"## {heading}\n" + "\n".join(f"- {item}" for item in items))
        return "\n\n".join(sections).strip()

    @staticmethod
    def _markdown_to_basic_html(markdown: str) -> str:
        lines = markdown.splitlines()
        html_lines: list[str] = []
        in_list = False
        for line in lines:
            if line.startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{html.escape(line[2:].strip())}</li>")
                continue
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if line.startswith("# "):
                html_lines.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            elif line.strip():
                html_lines.append(f"<p>{html.escape(line.strip())}</p>")
        if in_list:
            html_lines.append("</ul>")
        return "\n".join(html_lines)

    @staticmethod
    def _response_from_result(
        result: AIProviderResult,
        *,
        fallback_title: str = "",
    ) -> AIJobDescriptionResponse:
        data = result.parsed_payload
        if data is None and result.content:
            try:
                data = json.loads(result.content)
            except json.JSONDecodeError:
                data = {"title": fallback_title, "markdown": result.content}
        payload = AIJobDescriptionService._normalize_payload(data, fallback_title=fallback_title)
        return AIJobDescriptionResponse(
            generated_description=payload.markdown,
            **payload.model_dump(),
            usage=AIUsageSchema(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                provider=result.provider,
                model=result.model_id,
                latency_ms=result.latency_ms,
                cost_estimate_usd=result.cost_estimate_usd,
            ),
        )

    @staticmethod
    async def generate_description(
        session: AsyncSession,
        *,
        payload: dict,
        employer: EmployerProfile,
        request: AIJobDescriptionGenerateRequest,
    ) -> AIJobDescriptionResponse | AIJobDescriptionSectionResponse:
        user_id = UUID(str(payload.get("user_id")))
        config = AIJobDescriptionService._provider_config()
        AIJobDescriptionService._check_rate_limit(user_id, config)
        validator = await AIJobDescriptionService._enforce_subscription(session, user_id)
        await AIJobDescriptionService._validate_job_ownership(
            session=session,
            employer=employer,
            job_id=request.job_id,
        )
        section = AIJobDescriptionService._canonical_section(request.section)
        if section:
            result = await AIJobDescriptionService._call_section_ai_provider(
                AIJobDescriptionService._section_generation_prompt(request, section),
                section=section,
                operation="generate",
                config=config,
            )
            AIJobDescriptionService._validate_ai_result(result, config)
            await AIJobDescriptionService._record_success(
                session,
                validator=validator,
                employer=employer,
                user_id=user_id,
                operation_type=f"generate_{section}",
                job_id=request.job_id,
                result=result,
                config=config,
            )
            return AIJobDescriptionService._response_from_section_result(result, section=section)
        cache_key = AIJobDescriptionService._cache_key("generate", request, config)
        cached = await AIJobDescriptionService._cache_get(cache_key)
        if cached:
            return cached
        result = await AIJobDescriptionService._call_ai_provider(
            AIJobDescriptionService._generation_prompt(request),
            operation="generate",
            config=config,
        )
        AIJobDescriptionService._validate_ai_result(result, config)
        await AIJobDescriptionService._record_success(
            session,
            validator=validator,
            employer=employer,
            user_id=user_id,
            operation_type="generate",
            job_id=request.job_id,
            result=result,
            config=config,
        )
        response = AIJobDescriptionService._response_from_result(
            result,
            fallback_title=request.job_title,
        )
        await AIJobDescriptionService._cache_set(cache_key, response, config.cache_ttl_seconds)
        return response

    @staticmethod
    async def improve_description(
        session: AsyncSession,
        *,
        payload: dict,
        employer: EmployerProfile,
        request: AIJobDescriptionImproveRequest,
    ) -> AIJobDescriptionResponse | AIJobDescriptionSectionResponse:
        user_id = UUID(str(payload.get("user_id")))
        config = AIJobDescriptionService._provider_config()
        AIJobDescriptionService._check_rate_limit(user_id, config)
        validator = await AIJobDescriptionService._enforce_subscription(session, user_id)
        await AIJobDescriptionService._validate_job_ownership(
            session=session,
            employer=employer,
            job_id=request.job_id,
        )
        section = AIJobDescriptionService._canonical_section(request.section)
        if section:
            result = await AIJobDescriptionService._call_section_ai_provider(
                AIJobDescriptionService._section_rewrite_prompt(
                    section=section,
                    existing_description=request.existing_description,
                    instructions=request.additional_instructions,
                    tone=request.tone,
                ),
                section=section,
                operation="improve",
                config=config,
            )
            AIJobDescriptionService._validate_ai_result(result, config)
            await AIJobDescriptionService._record_success(
                session,
                validator=validator,
                employer=employer,
                user_id=user_id,
                operation_type=f"improve_{section}",
                job_id=request.job_id,
                result=result,
                config=config,
            )
            return AIJobDescriptionService._response_from_section_result(result, section=section)
        cache_key = AIJobDescriptionService._cache_key("improve", request, config)
        cached = await AIJobDescriptionService._cache_get(cache_key)
        if cached:
            return cached
        result = await AIJobDescriptionService._call_ai_provider(
            AIJobDescriptionService._improvement_prompt(request),
            operation="improve",
            config=config,
        )
        AIJobDescriptionService._validate_ai_result(result, config)
        await AIJobDescriptionService._record_success(
            session,
            validator=validator,
            employer=employer,
            user_id=user_id,
            operation_type="improve",
            job_id=request.job_id,
            result=result,
            config=config,
        )
        response = AIJobDescriptionService._response_from_result(result)
        await AIJobDescriptionService._cache_set(cache_key, response, config.cache_ttl_seconds)
        return response

    @staticmethod
    async def regenerate_section(
        session: AsyncSession,
        *,
        payload: dict,
        employer: EmployerProfile,
        request: AIJobDescriptionRegenerateRequest,
    ) -> AIJobDescriptionSectionResponse:
        user_id = UUID(str(payload.get("user_id")))
        config = AIJobDescriptionService._provider_config()
        AIJobDescriptionService._check_rate_limit(user_id, config)
        validator = await AIJobDescriptionService._enforce_subscription(session, user_id)
        await AIJobDescriptionService._validate_job_ownership(
            session=session,
            employer=employer,
            job_id=request.job_id,
        )
        section = AIJobDescriptionService._canonical_section(request.section)
        result = await AIJobDescriptionService._call_section_ai_provider(
            AIJobDescriptionService._section_rewrite_prompt(
                section=section,
                existing_description=request.existing_description,
                instructions=request.instructions,
                tone=request.tone,
            ),
            section=section,
            operation="regenerate",
            config=config,
        )
        AIJobDescriptionService._validate_ai_result(result, config)
        await AIJobDescriptionService._record_success(
            session,
            validator=validator,
            employer=employer,
            user_id=user_id,
            operation_type=f"regenerate_{section}",
            job_id=request.job_id,
            result=result,
            config=config,
        )
        return AIJobDescriptionService._response_from_section_result(result, section=section)

    @staticmethod
    async def stream_generate_description(
        session: AsyncSession,
        *,
        payload: dict,
        employer: EmployerProfile,
        request: AIJobDescriptionGenerateRequest,
    ):
        response = await AIJobDescriptionService.generate_description(
            session=session,
            payload=payload,
            employer=employer,
            request=request,
        )
        for chunk in response.generated_description.splitlines(keepends=True):
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True, 'usage': response.usage.model_dump()})}\n\n"


def _coerce_ats_score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 90
    return max(0, min(parsed, 100))
