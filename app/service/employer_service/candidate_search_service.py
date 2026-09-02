from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.employer_repository.candidate_search_repo import (
    EmployerCandidateSearchRepository,
)
from app.utils.image_urls import resolve_profile_image_url
from app.schema.invitations import (
    CandidateSearchRequest,
    CandidateSearchResponse,
    CandidateSummary,
)
from app.service.subscription.subscription_validator import SubscriptionValidator


def _full_name(user) -> str:
    return " ".join(
        part
        for part in (
            getattr(user, "first_name", None),
            getattr(user, "middle_name", None),
            getattr(user, "last_name", None),
        )
        if part
    )


def _extract_list(value: Any, key: str) -> list:
    if not isinstance(value, dict):
        return []
    raw = value.get(key)
    return raw if isinstance(raw, list) else []


def _skill_names(profile, resume_detail) -> List[str]:
    seen = set()
    names = []
    if resume_detail and isinstance(resume_detail.skills_json, dict):
        skills = _extract_list(resume_detail.skills_json, "skills")
        for skill in skills:
            if isinstance(skill, dict):
                name = skill.get("name") or skill.get("skill") or skill.get("title")
                if name and str(name).casefold() not in seen:
                    seen.add(str(name).casefold())
                    names.append(str(name))
            elif skill:
                key = str(skill).casefold()
                if key not in seen:
                    seen.add(key)
                    names.append(str(skill))
        if names:
            return names[:5]

    summary = getattr(profile, "skills_summary", None)
    if not summary:
        return []
    for part in str(summary).split(","):
        name = part.strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names[:5]


def _education_summary(resume_detail) -> Optional[str]:
    if not resume_detail or not isinstance(resume_detail.education_json, dict):
        return None
    education = _extract_list(resume_detail.education_json, "education")
    if not education:
        return None
    first = education[0]
    if not isinstance(first, dict):
        return str(first)
    parts = [
        first.get("degree") or first.get("qualification"),
        first.get("institution") or first.get("school") or first.get("university"),
    ]
    return ", ".join(str(part) for part in parts if part) or None


def _current_designation(resume_detail) -> Optional[str]:
    if not resume_detail or not isinstance(resume_detail.experience_json, dict):
        return None
    experience = _extract_list(resume_detail.experience_json, "experience")
    if not experience:
        return None
    current = next(
        (
            item
            for item in experience
            if isinstance(item, dict)
            and (
                item.get("currently_working")
                or item.get("current_company_flag")
                or item.get("is_current")
            )
        ),
        None,
    )
    first = current or next((item for item in experience if isinstance(item, dict)), None)
    if not first:
        return None
    return first.get("designation") or first.get("role") or first.get("title")


class EmployerCandidateSearchService:
    @staticmethod
    async def search_candidates(
        *,
        session: AsyncSession,
        payload: dict,
        filters: CandidateSearchRequest,
    ) -> CandidateSearchResponse:
        user_id = payload.get("user_id")
        validator = SubscriptionValidator(
            session=session,
            user_id=user_id,
            role="EMPLOYER",
        )
        await validator.require_feature("candidate_search")

        total, rows = await EmployerCandidateSearchRepository.search_candidates(
            session,
            filters=filters,
        )
        items = [
            CandidateSummary(
                candidate_id=profile.candidate_id,
                full_name=_full_name(user),
                profile_photo=resolve_profile_image_url(
                    getattr(user, "profile_image_url", None)
                ),
                profile_headline=profile.headline,
                profile_completion=profile.profile_completion_pct,
                current_company=profile.current_company,
                current_designation=_current_designation(resume_detail),
                experience=float(profile.total_experience)
                if profile.total_experience is not None
                else None,
                years_of_experience=float(profile.total_experience)
                if profile.total_experience is not None
                else None,
                location=profile.current_location,
                top_skills=_skill_names(profile, resume_detail),
                highest_education=_education_summary(resume_detail),
                education_summary=_education_summary(resume_detail),
                resume_available=bool(profile.active_resume_id or resume_detail),
                open_to_work=bool(profile.open_to_work),
                expected_salary=profile.salary_expectation,
                notice_period=profile.notice_period,
                availability=profile.notice_period,
                profile_completion_percentage=profile.profile_completion_pct,
                last_updated=profile.updated_at,
            )
            for profile, user, resume_detail in rows
        ]
        return CandidateSearchResponse(
            page=filters.page,
            page_size=filters.page_size,
            total_records=total,
            items=items,
        )
