"""Candidate ATS resume analysis using the shared Bedrock ``AIService``."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.candidate_repo import CandidateProfileRepo
from app.repository.candidate_repository.candidate_job_recommendation_repo import CandidateJobRecommendationRepo
from app.schema.ats_resume_analysis import ATSResumeAnalysisRequest, ATSResumeAnalysisResponse
from app.service import s3_service
from app.service.ai_service import AIService, AIServiceError, ai_error_status_code
from app.utils import resume_extraction

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 2400


class ATSResumeAnalysisService:
    """Loads only the authenticated candidate's resume and requests a structured ATS review."""

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    async def analyze(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: ATSResumeAnalysisRequest,
    ) -> ATSResumeAnalysisResponse:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(session, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        resume_data = await self._load_resume_data(session, profile.candidate_id, request.resume_id)
        system_prompt, user_prompt = self._build_prompt(resume_data, request.job_description)

        try:
            raw = self._ai_service.invoke_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=0.1,
            )
        except AIServiceError as exc:
            logger.warning("ATS resume analysis provider failure for candidate_id=%s: %s", profile.candidate_id, exc)
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail="The ATS analyzer is temporarily unavailable. Please try again shortly.",
            ) from exc

        try:
            response = ATSResumeAnalysisResponse.model_validate(raw)
        except ValidationError as exc:
            logger.warning("ATS resume analysis returned invalid structured output for candidate_id=%s", profile.candidate_id)
            raise HTTPException(
                status_code=502,
                detail="The ATS analyzer returned an invalid result. Please try again shortly.",
            ) from exc

        if bool(request.job_description) != bool(response.job_specific_analysis):
            logger.warning("ATS resume analysis returned an unexpected job-specific section for candidate_id=%s", profile.candidate_id)
            raise HTTPException(status_code=502, detail="The ATS analyzer returned an invalid result. Please try again shortly.")
        return response

    async def _load_resume_data(self, session: AsyncSession, candidate_id: str, resume_id: Optional[str]) -> dict[str, Any]:
        if resume_id:
            resume = await CandidateProfileRepo.get_resume(session, candidate_id, resume_id)
            if not resume:
                raise HTTPException(status_code=404, detail="Resume not found")
            if not resume.blob_ref:
                raise HTTPException(status_code=404, detail="Resume file not found")
            content, content_type = s3_service.fetch_object_bytes(resume.blob_ref)
            parsed = resume_extraction.extract_resume_data(content, resume.file_name or "", content_type)
            if not parsed:
                raise HTTPException(status_code=400, detail="The selected resume could not be analyzed. Please upload a readable PDF or Word document.")
            return parsed

        detail = await CandidateJobRecommendationRepo.get_latest_resume_detail(session, candidate_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Resume not found")
        resume_data = {
            "experience": (detail.experience_json or {}).get("experience") or [],
            "education": (detail.education_json or {}).get("education") or [],
            "skills": (detail.skills_json or {}).get("skills") or [],
            "projects": (detail.projects_json or {}).get("projects") or [],
            "certifications": (detail.certifications_json or {}).get("certifications") or [],
            "languages": (detail.languages_json or {}).get("languages") or [],
        }
        if not any(resume_data.values()):
            raise HTTPException(status_code=400, detail="The saved resume has no analyzable content")
        return resume_data

    @staticmethod
    def _build_prompt(resume_data: dict[str, Any], job_description: Optional[str]) -> tuple[str, str]:
        system_prompt = """You are a careful Applicant Tracking System (ATS) resume analyst. Analyze only the resume and optional job description supplied. Do not invent candidate qualifications, jobs, dates, degrees, certifications, skills, or results. Give actionable, concise suggestions and distinguish missing evidence from missing capability.

Return ONLY a JSON object with this exact shape:
{
  "general_analysis": {
    "scores": {"overall_score": 0, "keyword_skill_match_score": 0, "experience_relevance_score": 0, "resume_structure_formatting_score": 0, "content_quality_score": 0},
    "detected_skills": ["..."], "detected_roles": ["..."],
    "missing_keywords_or_skills": ["..."], "detected_issues": ["..."], "improvement_suggestions": ["..."]
  },
  "job_specific_analysis": null
}

Every score must be an integer from 0 to 100. General analysis must assess skills/keywords, roles, experience, education, projects, certifications, structure/formatting, and weak or missing information. If no job description is provided, job_specific_analysis MUST be null. If one is provided, replace null with an object containing: job_specific_score (0-100), matched_keywords_or_skills, missing_keywords_or_skills, experience_relevance_score (0-100), detected_issues, and improvement_suggestions. The job-specific section must only compare against that job description."""
        user_prompt = "RESUME DATA (candidate-provided):\n" + json.dumps(resume_data, ensure_ascii=False, default=str)
        if job_description:
            user_prompt += "\n\nJOB DESCRIPTION (for the separate job-specific analysis):\n" + job_description
        return system_prompt, user_prompt
