from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.utils.utc import utc_now
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    APPLICANT_RANKING_DETERMINISTIC_WEIGHT,
    APPLICANT_RANKING_LLM_ENABLED,
    APPLICANT_RANKING_SEMANTIC_WEIGHT,
)
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.employer_model.candidate_recommendation import CandidateRecommendation
from app.model.employer_model.job import Job
from app.repository.employer_repository.job_applicants_repo import JobApplicantsRepo
from app.service.candidate_job_recommendation_engine import (
    CandidateMatchContext,
    JobMatchContext,
    compute_skill_match,
    score_job_for_candidate,
)
from app.service.employer_service.ai_service import AIService, AIServiceError


logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 5000
MAX_RESUME_CONTEXT_CHARS = 12000
MAX_RESUME_SECTION_CHARS = 2500
MAX_RESUME_ITEM_CHARS = 900
APPLICANT_RANKING_PROMPT_VERSION = "applicant_ranking_semantic_v1"
PRIVATE_RESUME_KEYS = {
    "email",
    "phone",
    "mobile",
    "mobile_number",
    "contact",
    "address",
    "dob",
    "date_of_birth",
    "gender",
    "marital_status",
    "photo",
    "profile_image",
}
RESUME_SECTION_SPECS = (
    ("skills", "skills_json", "skills", 1),
    ("experience", "experience_json", "experience", 2),
    ("projects", "projects_json", "projects", 3),
    ("education", "education_json", "education", 4),
    ("certifications", "certifications_json", "certifications", 5),
    ("languages", "languages_json", "languages", 6),
)


class ApplicantSemanticMatchPayload(BaseModel):
    semantic_score: float = Field(..., ge=0, le=100)
    reasons: list[str] = Field(default_factory=list, max_length=4)
    missing_requirements: list[str] = Field(default_factory=list, max_length=8)


@dataclass
class ApplicantRankingResult:
    match_score: float
    match_label: str
    match_reasons: list[str]
    missing_requirements: list[str]


@dataclass
class SemanticMatchResult:
    score: Optional[float]
    reasons: list[str]
    missing_requirements: list[str]
    ai_metadata: dict | None = None


@dataclass
class ResumeSemanticContext:
    data: dict[str, Any]
    metadata: dict[str, Any]


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_list(value: Any, key: str) -> list:
    if isinstance(value, dict):
        raw = value.get(key)
        return raw if isinstance(raw, list) else []
    return value if isinstance(value, list) else []


def _extract_skill_names(skills_json: Any) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in _extract_list(skills_json, "skills"):
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill") or item.get("title")
        else:
            name = item
        if not name:
            continue
        text = str(name).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _extract_experience_text(experience_json: Any) -> str:
    parts: list[str] = []
    for item in _extract_list(experience_json, "experience"):
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("designation") or item.get("title")
        company = item.get("company")
        highlights = item.get("key_highlights") or item.get("description")
        text = " | ".join(str(part) for part in (role, company, highlights) if part)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _extract_education_text(education_json: Any) -> str:
    parts: list[str] = []
    for item in _extract_list(education_json, "education"):
        if isinstance(item, dict):
            text = " ".join(
                str(part)
                for part in (
                    item.get("degree") or item.get("qualification"),
                    item.get("field_of_study"),
                    item.get("institution") or item.get("school") or item.get("university"),
                )
                if part
            )
        else:
            text = str(item)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _normalize_score(score: Optional[float]) -> Optional[float]:
    if score is None:
        return None
    return round(max(0.0, min(100.0, float(score))), 2)


def _match_label(score: float) -> str:
    if score >= 85:
        return "Strong Match"
    if score >= 70:
        return "Good Match"
    if score >= 50:
        return "Moderate Match"
    return "Low Match"


def _limited(items: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))


def _clip_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:limit]


def _clean_resume_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, child in value.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in PRIVATE_RESUME_KEYS:
                continue
            cleaned_child = _clean_resume_value(child)
            if cleaned_child not in (None, "", [], {}):
                cleaned[str(key)] = cleaned_child
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            cleaned_item = _clean_resume_value(item)
            if cleaned_item not in (None, "", [], {}):
                cleaned_items.append(cleaned_item)
        return cleaned_items
    if isinstance(value, (str, int, float, bool)):
        return _clip_text(value, MAX_RESUME_ITEM_CHARS) if isinstance(value, str) else value
    return _clip_text(value, MAX_RESUME_ITEM_CHARS)


def _section_payload(raw_value: Any, section_key: str) -> Any:
    values = _extract_list(raw_value, section_key)
    if values:
        return _clean_resume_value(values)
    return _clean_resume_value(raw_value)


def _truncate_section_to_budget(value: Any, budget: int) -> tuple[Any, bool]:
    serialized = _stable_json(value)
    if len(serialized) <= budget:
        return value, False
    if isinstance(value, list):
        kept: list[Any] = []
        for item in value:
            candidate = [*kept, item]
            if len(_stable_json(candidate)) > budget:
                break
            kept.append(item)
        return kept, True
    if isinstance(value, dict):
        kept: dict[str, Any] = {}
        for key, item in value.items():
            candidate = {**kept, key: item}
            if len(_stable_json(candidate)) > budget:
                break
            kept[key] = item
        return kept, True
    return _clip_text(value, budget), True


def _resume_semantic_context(resume_detail: Optional[CandidateResumeDetail]) -> ResumeSemanticContext:
    if not resume_detail:
        return ResumeSemanticContext(
            data={},
            metadata={
                "resume_context_used": False,
                "resume_sections_used": [],
                "resume_sections_truncated": [],
                "resume_context_chars": 0,
                "resume_total_available_chars": 0,
                "resume_context_truncated": False,
            },
        )

    ordered_sections: list[tuple[int, str, Any, bool, int]] = []
    total_available_chars = 0
    for name, attr, section_key, priority in RESUME_SECTION_SPECS:
        raw_value = getattr(resume_detail, attr, None)
        payload = _section_payload(raw_value, section_key)
        if payload in (None, "", [], {}):
            continue
        available_chars = len(_stable_json(payload))
        total_available_chars += available_chars
        section_payload, section_truncated = _truncate_section_to_budget(
            payload,
            MAX_RESUME_SECTION_CHARS,
        )
        ordered_sections.append(
            (priority, name, section_payload, section_truncated, available_chars)
        )

    context: dict[str, Any] = {}
    truncated_sections: list[str] = []
    context_truncated = False
    for _, name, payload, section_truncated, _ in sorted(ordered_sections, key=lambda item: item[0]):
        candidate = {**context, name: payload}
        if len(_stable_json(candidate)) > MAX_RESUME_CONTEXT_CHARS:
            context_truncated = True
            truncated_sections.append(name)
            continue
        context[name] = payload
        if section_truncated:
            truncated_sections.append(name)

    return ResumeSemanticContext(
        data=context,
        metadata={
            "resume_context_used": bool(context),
            "resume_sections_used": list(context.keys()),
            "resume_sections_truncated": truncated_sections,
            "resume_context_chars": len(_stable_json(context)) if context else 0,
            "resume_total_available_chars": total_available_chars,
            "resume_context_truncated": context_truncated or bool(truncated_sections),
            "resume_detail_generated_at": getattr(resume_detail, "generated_at", None),
        },
    )


class ApplicantRankingService:
    @classmethod
    async def rank_applicant(
        cls,
        *,
        session: AsyncSession,
        employer_id: str,
        application,
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> ApplicantRankingResult:
        deterministic = cls._score_deterministic(profile, job, resume_detail)
        cached = await JobApplicantsRepo.get_cached_candidate_recommendation(
            session,
            job_id=job.job_id,
            candidate_id=profile.candidate_id,
            application_id=application.application_id,
        )

        if cached and cls._cache_is_fresh(cached, profile, job, resume_detail):
            return ApplicantRankingResult(
                match_score=round(float(cached.match_score or deterministic.score), 2),
                match_label=cached.match_label or _match_label(float(cached.match_score or deterministic.score)),
                match_reasons=list(cached.match_reasons or deterministic.reasons),
                missing_requirements=list(cached.missing_requirements or cls._missing_requirements(profile, job, resume_detail)),
            )

        semantic = await cls._score_semantic(profile, job, resume_detail)
        final_score = cls._blend_scores(deterministic.score, semantic.score)
        missing = _limited(
            semantic.missing_requirements
            or cls._missing_requirements(profile, job, resume_detail),
            8,
        )
        reasons = _limited([*deterministic.reasons, *semantic.reasons], 6)
        if not reasons:
            reasons = ["Applicant was ranked using available profile and job requirement signals."]

        saved = await cls._save_cache(
            session=session,
            cached=cached,
            employer_id=employer_id,
            application=application,
            profile=profile,
            job=job,
            resume_detail=resume_detail,
            deterministic_score=deterministic.score,
            semantic_score=semantic.score,
            final_score=final_score,
            reasons=reasons,
            missing_requirements=missing,
            breakdown=deterministic.breakdown,
            semantic_ai_metadata=semantic.ai_metadata,
        )

        return ApplicantRankingResult(
            match_score=round(float(saved.match_score or final_score), 2),
            match_label=saved.match_label or _match_label(final_score),
            match_reasons=list(saved.match_reasons or reasons),
            missing_requirements=list(saved.missing_requirements or missing),
        )

    @staticmethod
    def _score_deterministic(
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ):
        candidate_context = ApplicantRankingService._candidate_context(profile, resume_detail)
        job_context = ApplicantRankingService._job_context(job)
        return score_job_for_candidate(candidate_context, job_context)

    @staticmethod
    def _candidate_context(
        profile: CandidateProfile,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> CandidateMatchContext:
        skills = set()
        if resume_detail:
            for skill in _extract_skill_names(resume_detail.skills_json):
                skills.add(skill.lower())
        if getattr(profile, "skills_summary", None):
            for part in str(profile.skills_summary).replace(";", ",").split(","):
                part = part.strip()
                if part:
                    skills.add(part.lower())

        preferred_titles = set()
        if getattr(profile, "target_roles", None):
            for part in str(profile.target_roles).replace(";", ",").split(","):
                part = part.strip()
                if part:
                    preferred_titles.add(part)

        current_designation = getattr(profile, "headline", None)
        if resume_detail:
            for item in _extract_list(resume_detail.experience_json, "experience"):
                if isinstance(item, dict):
                    current_designation = (
                        item.get("role")
                        or item.get("designation")
                        or item.get("title")
                        or current_designation
                    )
                    break

        return CandidateMatchContext(
            skills=skills,
            total_experience_years=_to_float(getattr(profile, "total_experience", None)),
            headline=getattr(profile, "headline", None),
            current_designation=current_designation,
            preferred_titles=preferred_titles,
            current_location=getattr(profile, "current_location", None),
            preferred_location=getattr(profile, "preferred_location", None),
            desired_employment_type=getattr(profile, "desired_employment", None),
            work_preference=getattr(profile, "work_preference", None),
            expected_salary_min=_to_float(getattr(profile, "expected_ctc", None)),
            expected_salary_max=_to_float(getattr(profile, "expected_ctc", None)),
            profile_completion_pct=getattr(profile, "profile_completion_pct", 0) or 0,
        )

    @staticmethod
    def _job_context(job: Job) -> JobMatchContext:
        skills = {s.skill.strip().lower() for s in (getattr(job, "skills", None) or []) if getattr(s, "skill", None)}
        return JobMatchContext(
            job_id=job.job_id,
            title=getattr(job, "title", None) or "",
            required_skills=skills,
            preferred_skills=set(),
            experience_min=getattr(job, "experience_min", None),
            experience_max=getattr(job, "experience_max", None),
            location=getattr(job, "location", None),
            employment_type=getattr(job, "employment_type", None),
            work_mode=getattr(job, "work_mode", None),
            salary_min=getattr(job, "salary_min", None),
            salary_max=getattr(job, "salary_max", None),
        )

    @staticmethod
    def _missing_requirements(
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> list[str]:
        candidate = ApplicantRankingService._candidate_context(profile, resume_detail)
        job_context = ApplicantRankingService._job_context(job)
        detail = compute_skill_match(
            candidate.skills,
            job_context.required_skills,
            job_context.preferred_skills,
        )
        missing = list(detail.missing_required_skills)

        experience_min = getattr(job, "experience_min", None)
        if experience_min is not None and candidate.total_experience_years is not None:
            if candidate.total_experience_years < experience_min:
                missing.append(f"{experience_min}+ years experience")
        location = getattr(job, "location", None)
        if location and not (candidate.current_location or candidate.preferred_location):
            missing.append(f"Location: {location}")
        return _limited(missing, 8)

    @staticmethod
    def _blend_scores(deterministic_score: float, semantic_score: Optional[float]) -> float:
        deterministic = _normalize_score(deterministic_score) or 0.0
        semantic = _normalize_score(semantic_score)
        if semantic is None:
            return round(deterministic, 2)

        total_weight = APPLICANT_RANKING_DETERMINISTIC_WEIGHT + APPLICANT_RANKING_SEMANTIC_WEIGHT
        if total_weight <= 0:
            return round(deterministic, 2)
        score = (
            deterministic * APPLICANT_RANKING_DETERMINISTIC_WEIGHT
            + semantic * APPLICANT_RANKING_SEMANTIC_WEIGHT
        ) / total_weight
        return round(_normalize_score(score) or deterministic, 2)

    @staticmethod
    def _cache_is_fresh(
        cached: CandidateRecommendation,
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> bool:
        return (
            cached.job_updated_at_snapshot == getattr(job, "updated_at", None)
            and cached.candidate_updated_at_snapshot == getattr(profile, "updated_at", None)
            and cached.resume_detail_generated_at_snapshot
            == (getattr(resume_detail, "generated_at", None) if resume_detail else None)
        )

    @staticmethod
    async def _save_cache(
        *,
        session: AsyncSession,
        cached: Optional[CandidateRecommendation],
        employer_id: str,
        application,
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
        deterministic_score: float,
        semantic_score: Optional[float],
        final_score: float,
        reasons: list[str],
        missing_requirements: list[str],
        breakdown: dict,
        semantic_ai_metadata: Optional[dict] = None,
    ) -> CandidateRecommendation:
        row = cached or CandidateRecommendation(
            recommendation_id=uuid.uuid4().hex,
            employer_id=employer_id,
            candidate_id=profile.candidate_id,
            job_id=job.job_id,
        )
        row.application_id = application.application_id
        row.match_score = final_score
        row.deterministic_score = _normalize_score(deterministic_score)
        row.semantic_score = _normalize_score(semantic_score)
        row.match_label = _match_label(final_score)
        row.match_reasons = reasons
        row.missing_requirements = missing_requirements
        row.score_breakdown = {
            **(breakdown or {}),
            "semantic_ai": semantic_ai_metadata or {},
        }
        row.job_updated_at_snapshot = getattr(job, "updated_at", None)
        row.candidate_updated_at_snapshot = getattr(profile, "updated_at", None)
        row.resume_detail_generated_at_snapshot = (
            getattr(resume_detail, "generated_at", None) if resume_detail else None
        )
        row.generated_at = utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return await JobApplicantsRepo.save_candidate_recommendation(session, row)

    @staticmethod
    async def _score_semantic(
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> SemanticMatchResult:
        if not APPLICANT_RANKING_LLM_ENABLED:
            return SemanticMatchResult(score=None, reasons=[], missing_requirements=[], ai_metadata=None)

        prompt, resume_metadata = ApplicantRankingService._semantic_prompt(
            profile,
            job,
            resume_detail,
        )
        try:
            data = await ApplicantRankingService._invoke_semantic_bedrock(prompt)
        except AIServiceError:
            logger.warning(
                "Applicant ranking semantic score failed; falling back to deterministic score.",
                exc_info=True,
            )
            return SemanticMatchResult(score=None, reasons=[], missing_requirements=[])

        return SemanticMatchResult(
            score=_normalize_score(data.get("semantic_score")),
            reasons=_limited([str(item) for item in data.get("reasons", []) if item], 4),
            missing_requirements=_limited(
                [str(item) for item in data.get("missing_requirements", []) if item],
                8,
            ),
            ai_metadata={
                **(data.get("_ai_metadata") if isinstance(data.get("_ai_metadata"), dict) else {}),
                "resume_context": resume_metadata,
            },
        )

    @staticmethod
    def _semantic_prompt(
        profile: CandidateProfile,
        job: Job,
        resume_detail: Optional[CandidateResumeDetail],
    ) -> tuple[str, dict[str, Any]]:
        resume_context = _resume_semantic_context(resume_detail)
        candidate_text = {
            "headline": getattr(profile, "headline", None),
            "summary": getattr(profile, "summary", None),
            "skills": list(ApplicantRankingService._candidate_context(profile, resume_detail).skills),
            "experience_years": _to_float(getattr(profile, "total_experience", None)),
            "current_location": getattr(profile, "current_location", None),
            "preferred_location": getattr(profile, "preferred_location", None),
            "work_preference": getattr(profile, "work_preference", None),
            "desired_employment": getattr(profile, "desired_employment", None),
            "resume_context": resume_context.data,
            "resume_context_metadata": resume_context.metadata,
        }
        job_text = {
            "title": getattr(job, "title", None),
            "description": (getattr(job, "description", None) or "")[:MAX_TEXT_CHARS],
            "skills": [s.skill for s in (getattr(job, "skills", None) or []) if getattr(s, "skill", None)],
            "requirements": getattr(job, "requirements", None) or [],
            "responsibilities": getattr(job, "responsibilities", None) or [],
            "experience_min": getattr(job, "experience_min", None),
            "experience_max": getattr(job, "experience_max", None),
            "education": getattr(job, "education", None),
            "location": getattr(job, "location", None),
            "work_mode": getattr(job, "work_mode", None),
            "employment_type": getattr(job, "employment_type", None),
        }
        return (
            json.dumps(
                {
                    "task": (
                        "Compare the applicant to this job using the full parsed resume_context "
                        "when available. Score only job-relevant evidence from profile, resume, "
                        "and job requirements. Prefer resume evidence over profile summary when "
                        "they conflict. Return semantic_score 0-100, reasons, and "
                        "missing_requirements. Do not include the applicant name, email, phone, "
                        "or demographic assumptions."
                    ),
                    "candidate": candidate_text,
                    "job": job_text,
                },
                default=str,
            ),
            resume_context.metadata,
        )

    @staticmethod
    async def _invoke_semantic_bedrock(prompt: str) -> dict:
        system_prompt = (
            "You are an applicant matching assistant. Score only job-relevant "
            "qualifications. Do not use protected or personal attributes. "
            "Return strict JSON only with this shape: "
            '{"semantic_score":0,"reasons":["..."],"missing_requirements":["..."]}.'
        )
        result = await AIService().ainvoke_json_with_usage(
            system_prompt=system_prompt,
            user_prompt=prompt,
            max_tokens=700,
            temperature=0.1,
            response_model=ApplicantSemanticMatchPayload,
            feature="applicant_ranking",
            prompt_version=APPLICANT_RANKING_PROMPT_VERSION,
        )
        data = dict(result.data)
        data["_ai_metadata"] = {
            "provider": result.provider,
            "model": result.model_id,
            "prompt_version": result.prompt_version,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "repaired": result.repaired,
            "repair_attempts": result.repair_attempts,
        }
        return data

