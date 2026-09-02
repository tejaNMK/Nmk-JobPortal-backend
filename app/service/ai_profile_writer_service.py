"""AI Resume / Profile Writer service.

Uses AWS Bedrock (via the existing `AIService`, the same reusable Bedrock
wrapper `JobMatchService` / AI Job Match Score uses) to rewrite the
logged-in candidate's Professional Headline, Professional Summary / About,
and Experience bullet descriptions into stronger, ATS-friendly, tailored
copy.

Data access is intentionally *not* duplicated: candidate profile + latest
resume detail are fetched via the same `CandidateJobRecommendationRepo`
helpers `JobMatchService` already relies on
(`get_candidate_profile`, `get_latest_resume_detail`,
`build_candidate_match_context`), so there is exactly one place in the
codebase that knows how to load "the logged-in candidate's profile +
resume for an AI feature."

Fabrication safety
-------------------
The one hard requirement this feature must never violate is "free of
fabricated information (only enhance existing content)". Two different
techniques enforce that, matched to what each section actually is:

* Headline / About have no fixed ground truth to check the model's answer
  against (they're free text), so faithfulness is enforced through prompt
  engineering: the system prompt explicitly forbids inventing employers,
  skills, titles, qualifications, or metrics not present in the supplied
  candidate context, and temperature is kept low (0.2) for faithfulness
  over creativity.
* Experience descriptions *do* have ground truth -- the candidate's own
  `role`/`company` per entry -- so those two fields are never taken from
  the AI response at all. Only the rewritten `description` text is taken
  from Bedrock; `title`/`company` are always echoed back from the
  candidate's own resume data, positionally matched. This makes it
  structurally impossible for a hallucinated employer/title to reach the
  response, regardless of what Bedrock returns.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.schema.ai_profile_writer import (
    ALL_SECTIONS,
    AIProfileExperienceEntry,
    AIProfileWriterLength,
    AIProfileWriterMode,
    AIProfileWriterResponse,
    AIProfileWriterSection,
    AIProfileWriterTone,
)
from app.service.ai_service import AIService, AIServiceError

logger = logging.getLogger(__name__)

_MAX_EXPERIENCE_ENTRIES = 12  # keeps prompt size/cost bounded for very long resumes

# Per-mode sampling temperature for the transform modes (IMPROVE/REWRITE/
# MAKE_ATS_FRIENDLY/SHORTEN/EXPAND). GENERATE stays at the original 0.2 --
# drafting fresh copy from profile facts alone should stay conservative.
# The transform modes need enough freedom to actually produce a different
# result than the candidate's current draft; a headline/about that's
# already tight and well-written was otherwise coming back unchanged at
# 0.2, which looked like the "Improve" button silently doing nothing.
_MODE_TEMPERATURE: Dict[AIProfileWriterMode, float] = {
    AIProfileWriterMode.GENERATE: 0.2,
    AIProfileWriterMode.IMPROVE: 0.35,
    AIProfileWriterMode.REWRITE: 0.45,
    AIProfileWriterMode.MAKE_ATS_FRIENDLY: 0.3,
    AIProfileWriterMode.SHORTEN: 0.25,
    AIProfileWriterMode.EXPAND: 0.3,
}

# Reminder appended to the system prompt on a retry when the model's first
# attempt at a transform mode came back identical (or near-identical) to
# the candidate's existing draft -- mirrors the same fix already applied
# to the "Improve Writing / Shorter" text-assist feature.
_UNCHANGED_RETRY_REMINDER = (
    "REMINDER: your previous attempt returned this section essentially "
    "unchanged from the candidate's current draft -- that is not "
    "acceptable for this task. Produce a genuinely different rewrite "
    "this time (different phrasing/structure per the TASK above) while "
    "still preserving every fact from the draft."
)


class AIProfileWriterService:
    """Orchestrates the AI Resume/Profile Writer feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`), mirroring `JobMatchService`, so callers/tests can supply a
    fake/mocked implementation without monkeypatching module internals or
    touching boto3/Bedrock.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_profile_content(
        self,
        session: AsyncSession,
        user_id: UUID,
        target_role: Optional[str] = None,
        tone: Optional[AIProfileWriterTone] = None,
        length: Optional[AIProfileWriterLength] = None,
    ) -> Optional[AIProfileWriterResponse]:
        """Generate improved content for all supported sections at once
        (Headline + Professional Summary + Experience)."""

        return await self._generate(session, user_id, ALL_SECTIONS, target_role, tone=tone, length=length)

    async def regenerate_section(
        self,
        session: AsyncSession,
        user_id: UUID,
        section: AIProfileWriterSection,
        target_role: Optional[str] = None,
        tone: Optional[AIProfileWriterTone] = None,
        length: Optional[AIProfileWriterLength] = None,
        mode: AIProfileWriterMode = AIProfileWriterMode.GENERATE,
        existing_text: Optional[str] = None,
    ) -> Optional[AIProfileWriterResponse]:
        """Regenerate a single section without touching the others.

        When `mode` is anything other than `GENERATE`, `existing_text` (the
        candidate's current unsaved draft for that field) is transformed
        directly instead of drafting fresh copy from the profile alone --
        this is what powers the "Improve Writing / Rewrite / Make ATS
        Friendly / Shorten / Expand" actions in the UI.
        """

        return await self._generate(
            session,
            user_id,
            (section,),
            target_role,
            tone=tone,
            length=length,
            mode=mode,
            existing_text=existing_text,
        )

    # ------------------------------------------------------------------
    # Shared orchestration
    # ------------------------------------------------------------------

    async def _generate(
        self,
        session: AsyncSession,
        user_id: UUID,
        sections: tuple,
        target_role: Optional[str],
        tone: Optional[AIProfileWriterTone] = None,
        length: Optional[AIProfileWriterLength] = None,
        mode: AIProfileWriterMode = AIProfileWriterMode.GENERATE,
        existing_text: Optional[str] = None,
    ) -> Optional[AIProfileWriterResponse]:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(session, user_id)
        if not profile:
            return None

        resume_detail = await CandidateJobRecommendationRepo.get_latest_resume_detail(
            session, profile.candidate_id
        )
        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )

        experience_entries = self._extract_experience_entries(resume_detail)
        effective_target_role = (target_role or profile.target_roles or "").strip()

        needs_experience = AIProfileWriterSection.EXPERIENCE in sections
        if needs_experience and not experience_entries:
            # Nothing to enhance -- there is no source content, and this
            # feature must never fabricate a work history from scratch.
            sections = tuple(s for s in sections if s != AIProfileWriterSection.EXPERIENCE)
            if not sections:
                return AIProfileWriterResponse(experience=[])

        if mode != AIProfileWriterMode.GENERATE and not (existing_text or "").strip():
            raise HTTPException(
                status_code=400,
                detail=f"'existing_text' is required when mode is '{mode.value}'.",
            )

        candidate_text = self._build_candidate_text(
            profile, candidate_context.skills, experience_entries, effective_target_role
        )
        system_prompt, user_prompt = self._build_prompt(
            candidate_text,
            sections,
            experience_entries,
            effective_target_role,
            tone=tone,
            length=length,
            mode=mode,
            existing_text=existing_text,
        )

        try:
            raw = self._ai_service.invoke_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1800,
                temperature=_MODE_TEMPERATURE[mode],
            )
        except AIServiceError as exc:
            logger.error(
                "AI profile writer generation failed for candidate_id=%s, sections=%s: %s",
                profile.candidate_id,
                [s.value for s in sections],
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="AI profile writer is temporarily unavailable. Please try again shortly.",
            ) from exc

        response = self._to_response(raw, sections, experience_entries)

        if (
            mode != AIProfileWriterMode.GENERATE
            and (existing_text or "").strip()
            and self._transform_result_unchanged(sections, response, existing_text)
        ):
            # The model's first attempt came back essentially identical to
            # the candidate's current draft -- the bug behind "I clicked
            # Improve and the suggestion is exactly what I already had."
            # Retry once with an explicit reminder rather than silently
            # handing back a no-op "suggestion".
            logger.info(
                "AI profile writer %s produced an unchanged result for "
                "candidate_id=%s, section(s)=%s; retrying once.",
                mode.value,
                profile.candidate_id,
                [s.value for s in sections],
            )
            retry_system_prompt = "\n\n".join([system_prompt, _UNCHANGED_RETRY_REMINDER])
            try:
                retry_raw = self._ai_service.invoke_json(
                    system_prompt=retry_system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=1800,
                    temperature=_MODE_TEMPERATURE[mode],
                )
                response = self._to_response(retry_raw, sections, experience_entries)
            except AIServiceError as exc:
                # Retry failing shouldn't lose the first (valid, if
                # unchanged) response -- log and keep what we already have.
                logger.warning(
                    "AI profile writer %s retry failed for candidate_id=%s: %s",
                    mode.value,
                    profile.candidate_id,
                    exc,
                )

        if needs_experience and AIProfileWriterSection.EXPERIENCE not in sections:
            # Experience was dropped above because there was nothing to
            # rewrite; still return an explicit empty list rather than
            # omitting the key, so callers can tell "no experience on
            # file" apart from "section not requested".
            response.experience = []

        return response

    @staticmethod
    def _transform_result_unchanged(
        sections: tuple,
        response: AIProfileWriterResponse,
        existing_text: Optional[str],
    ) -> bool:
        """True if a transform mode's output is essentially identical to
        the candidate's existing draft for the single section being
        regenerated. Only meaningful for `regenerate_section` calls
        (exactly one of headline/about), since `existing_text` maps 1:1
        to a single string there -- EXPERIENCE's response is a list of
        entries, so it's intentionally excluded from this check."""

        if len(sections) != 1 or not existing_text:
            return False

        section = sections[0]
        if section == AIProfileWriterSection.HEADLINE:
            candidate_value = response.headline
        elif section == AIProfileWriterSection.ABOUT:
            candidate_value = response.professional_summary
        else:
            return False

        if not candidate_value:
            return False

        return " ".join(candidate_value.split()) == " ".join(existing_text.split())

    # ------------------------------------------------------------------
    # Candidate context building (mirrors JobMatchService's approach)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_experience_entries(
        resume_detail: Optional[CandidateResumeDetail],
    ) -> List[Dict[str, Any]]:
        """Pull structured experience entries straight from the
        candidate's own resume JSON. Returned dicts preserve the original
        `role`/`company`/dates/highlights so the response's `title` and
        `company` fields can always be sourced from here, never from the
        AI."""

        if not resume_detail or not resume_detail.experience_json:
            return []
        entries = resume_detail.experience_json.get("experience") or []

        cleaned: List[Dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("title") or "").strip()
            company = str(item.get("company") or "").strip()
            if not role and not company:
                continue
            cleaned.append(
                {
                    "role": role or "Team Member",
                    "company": company or "Not specified",
                    "start_date": str(item.get("start_date") or "").strip(),
                    "end_date": "Present" if item.get("currently_working") else str(item.get("end_date") or "").strip(),
                    "key_highlights": str(item.get("key_highlights") or "").strip(),
                }
            )
        return cleaned[:_MAX_EXPERIENCE_ENTRIES]

    @staticmethod
    def _build_candidate_text(
        profile: CandidateProfile,
        skills: set,
        experience_entries: List[Dict[str, Any]],
        target_role: str,
    ) -> str:
        lines: List[str] = []

        if profile.headline:
            lines.append(f"Current Headline: {profile.headline}")
        if profile.summary:
            lines.append(f"Current Professional Summary: {profile.summary}")
        if profile.total_experience is not None:
            lines.append(f"Total Experience: {profile.total_experience} years")
        if profile.current_company:
            lines.append(f"Current Company/Role: {profile.current_company}")
        if profile.experience_level:
            lines.append(f"Experience Level: {profile.experience_level}")
        if target_role:
            lines.append(f"Target Role: {target_role}")

        if skills:
            lines.append(f"Skills: {', '.join(sorted(skills))}")

        if experience_entries:
            lines.append("Work Experience (do not add, remove, or reorder entries):")
            for idx, entry in enumerate(experience_entries, start=1):
                dates = " - ".join(part for part in (entry["start_date"], entry["end_date"]) if part)
                header = f"{idx}. {entry['role']} at {entry['company']}"
                if dates:
                    header += f" ({dates})"
                lines.append(header)
                if entry["key_highlights"]:
                    lines.append(f"   Existing description: {entry['key_highlights']}")
                else:
                    lines.append("   Existing description: (none provided)")

        text = "\n".join(lines).strip()
        return text or "No profile or resume information available for this candidate."

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    _TONE_GUIDANCE = {
        AIProfileWriterTone.PROFESSIONAL: "formal, polished, and business-appropriate",
        AIProfileWriterTone.CONFIDENT: "confident and assertive, emphasizing impact and ownership",
        AIProfileWriterTone.FRIENDLY: "warm and approachable while remaining professional",
        AIProfileWriterTone.CONCISE: "crisp and to-the-point, no filler words",
        AIProfileWriterTone.ENTHUSIASTIC: "energetic and passionate about the work",
    }

    _LENGTH_GUIDANCE = {
        AIProfileWriterLength.SHORT: "very brief -- about 2 sentences (roughly 40-60 words)",
        AIProfileWriterLength.MEDIUM: "concise -- 3-5 sentences (roughly 60-120 words)",
        AIProfileWriterLength.LONG: "detailed -- 5-7 sentences (roughly 120-200 words)",
    }

    _MODE_INSTRUCTION = {
        AIProfileWriterMode.GENERATE: (
            "Draft fresh content for this section from the candidate profile "
            "and resume data below."
        ),
        AIProfileWriterMode.IMPROVE: (
            "The candidate has already written a draft for this section (see "
            "'CANDIDATE'S CURRENT DRAFT' below). Produce a genuinely "
            "improved rewrite -- stronger word choice, tighter phrasing, "
            "better flow -- not a copy of the draft with only trivial "
            "changes. The result must read as noticeably better than the "
            "draft while preserving its meaning, structure, and all the "
            "facts it contains. Use the candidate profile/resume data only "
            "as supporting context -- do not replace the substance of "
            "their draft."
        ),
        AIProfileWriterMode.REWRITE: (
            "The candidate has already written a draft for this section (see "
            "'CANDIDATE'S CURRENT DRAFT' below). Rewrite it from scratch with "
            "fresh phrasing and structure while keeping every fact it "
            "contains (roles, skills, employers, achievements) -- do not "
            "invent anything beyond what the draft and the candidate "
            "profile/resume data support."
        ),
        AIProfileWriterMode.MAKE_ATS_FRIENDLY: (
            "The candidate has already written a draft for this section (see "
            "'CANDIDATE'S CURRENT DRAFT' below). Rewrite it to be more ATS "
            "(Applicant Tracking System) friendly: work in relevant keywords "
            "and skills already present in the candidate's profile/resume "
            "data, use standard section phrasing and simple formatting, and "
            "avoid tables, symbols, or jargon that ATS parsers mishandle. "
            "Keep every fact the draft contains -- do not invent new ones."
        ),
        AIProfileWriterMode.SHORTEN: (
            "The candidate has already written a draft for this section (see "
            "'CANDIDATE'S CURRENT DRAFT' below). Shorten it -- keep only the "
            "strongest, most relevant points and tighten the language -- "
            "while preserving its core meaning and facts."
        ),
        AIProfileWriterMode.EXPAND: (
            "The candidate has already written a draft for this section (see "
            "'CANDIDATE'S CURRENT DRAFT' below). Expand it with more detail "
            "and impact, drawing ONLY on facts already present in the draft "
            "or in the candidate profile/resume data below -- never invent "
            "new employers, skills, or achievements to pad the length."
        ),
    }

    @staticmethod
    def _build_prompt(
        candidate_text: str,
        sections: tuple,
        experience_entries: List[Dict[str, Any]],
        target_role: str,
        tone: Optional[AIProfileWriterTone] = None,
        length: Optional[AIProfileWriterLength] = None,
        mode: AIProfileWriterMode = AIProfileWriterMode.GENERATE,
        existing_text: Optional[str] = None,
    ) -> tuple[str, str]:
        section_values = [s.value for s in sections]
        effective_tone = tone or AIProfileWriterTone.PROFESSIONAL
        effective_length = length or AIProfileWriterLength.MEDIUM

        key_instructions = []
        if AIProfileWriterSection.HEADLINE in sections:
            key_instructions.append(
                '- "headline": string, a single-line, ATS-friendly Professional '
                "Headline (max ~120 characters) that reflects the candidate's "
                "actual seniority, role, and top skills."
            )
        if AIProfileWriterSection.ABOUT in sections:
            key_instructions.append(
                '- "professional_summary": string, a Professional Summary / '
                "About section, written in first-person-omitted third person "
                "(no 'I'), that highlights the candidate's real experience, "
                "skills, and value proposition. Length: "
                f"{AIProfileWriterService._LENGTH_GUIDANCE[effective_length]}."
            )
        if AIProfileWriterSection.EXPERIENCE in sections and experience_entries:
            key_instructions.append(
                '- "experience": array with exactly '
                f"{len(experience_entries)} object(s), in the SAME ORDER as the "
                "candidate's Work Experience entries listed below (one output "
                "object per input entry, do not merge, skip, or add entries). "
                'Each object must contain only "description": string, a '
                "rewritten, ATS-friendly description of that role as 2-4 strong "
                "bullet points (join bullets with '\\n', each starting with an "
                "action verb and, where the existing description supports it, a "
                "quantifiable result). Do not include title or company in this "
                "object -- only \"description\"."
            )

        mode_instruction = AIProfileWriterService._MODE_INSTRUCTION[mode]
        tone_guidance = AIProfileWriterService._TONE_GUIDANCE[effective_tone]

        system_prompt = (
            "You are an expert resume writer and ATS (Applicant Tracking "
            "System) optimization specialist. You improve a candidate's "
            "profile content using ONLY the facts provided about them -- "
            "you NEVER invent employers, job titles, dates, skills, "
            "certifications, degrees, or metrics that are not present in "
            "the candidate information (or their current draft) given to "
            "you. If the existing content for a section is sparse, write a "
            "stronger version of what is there rather than adding new "
            "claims.\n\n"
            f"TASK: {mode_instruction}\n\n"
            f"TONE: Write in a tone that is {tone_guidance}.\n\n"
            "You MUST respond with ONLY a single valid JSON object and "
            "nothing else -- no markdown, no code fences, no explanations "
            "before or after the JSON. The JSON object must contain exactly "
            f"these keys ({', '.join(section_values)}):\n"
            + "\n".join(key_instructions)
            + "\n\nWrite professional, grammatically correct, and impactful "
            "content, tailored to the candidate's skills, experience, and "
            "target role when one is given. Return valid JSON only, with no "
            "trailing commentary."
        )

        user_prompt_parts = ["CANDIDATE PROFILE AND RESUME:", candidate_text, ""]
        if target_role:
            user_prompt_parts.append(f"Tailor the content toward this target role: {target_role}\n")
        if mode != AIProfileWriterMode.GENERATE and existing_text:
            user_prompt_parts.append("CANDIDATE'S CURRENT DRAFT (transform this text per the TASK above):")
            user_prompt_parts.append(existing_text.strip())
            user_prompt_parts.append("")
        user_prompt_parts.append(
            "Generate content for the following section(s): "
            f"{', '.join(section_values)}. Respond with the JSON object "
            "described in your instructions."
        )
        user_prompt = "\n".join(user_prompt_parts)

        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Response mapping / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        raw: Dict[str, Any],
        sections: tuple,
        experience_entries: List[Dict[str, Any]],
    ) -> AIProfileWriterResponse:
        headline: Optional[str] = None
        professional_summary: Optional[str] = None
        experience: Optional[List[AIProfileExperienceEntry]] = None

        if AIProfileWriterSection.HEADLINE in sections:
            value = raw.get("headline")
            headline = value.strip() if isinstance(value, str) else ""

        if AIProfileWriterSection.ABOUT in sections:
            value = raw.get("professional_summary")
            professional_summary = value.strip() if isinstance(value, str) else ""

        if AIProfileWriterSection.EXPERIENCE in sections and experience_entries:
            experience = AIProfileWriterService._merge_experience(
                raw.get("experience"), experience_entries
            )

        return AIProfileWriterResponse(
            headline=headline,
            professional_summary=professional_summary,
            experience=experience,
        )

    @staticmethod
    def _merge_experience(
        ai_experience: Any,
        experience_entries: List[Dict[str, Any]],
    ) -> List[AIProfileExperienceEntry]:
        """Positionally zip the AI's rewritten descriptions back onto the
        candidate's own title/company data. `title`/`company` are always
        sourced from `experience_entries` (the candidate's real resume
        data) -- never from `ai_experience` -- so a hallucinated employer
        or title from Bedrock can never surface in the response. If the AI
        response is missing, malformed, or short, the candidate's own
        existing description is used as a safe fallback instead of leaving
        the entry blank."""

        ai_list = ai_experience if isinstance(ai_experience, list) else []

        merged: List[AIProfileExperienceEntry] = []
        for idx, entry in enumerate(experience_entries):
            description = entry["key_highlights"]  # safe fallback: candidate's own text
            if idx < len(ai_list) and isinstance(ai_list[idx], dict):
                candidate_desc = ai_list[idx].get("description")
                if isinstance(candidate_desc, str) and candidate_desc.strip():
                    description = candidate_desc.strip()

            merged.append(
                AIProfileExperienceEntry(
                    title=entry["role"],
                    company=entry["company"],
                    description=description,
                )
            )
        return merged