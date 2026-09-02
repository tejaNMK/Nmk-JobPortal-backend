from __future__ import annotations

import html
import re
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.job import Job

from app.utils.slug import slugify_job_title

from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.schema.candidate_job_search import (
    CandidateJobCardResponse,
    CandidateCompanyInfoResponse,
    CandidateJobDetailsResponse,
    CandidateJobSearchResponse,
    CandidateJobSuggestionsResponse,
    CandidateRecruiterPublicInfoResponse,
)


class CandidateJobSearchService:
    JOB_DESCRIPTION_PREVIEW_CHARS = 120

    @staticmethod
    def _job_description_preview(description: Optional[str]) -> Optional[str]:
        if description is None:
            return None
        return description[: CandidateJobSearchService.JOB_DESCRIPTION_PREVIEW_CHARS]

    @staticmethod
    def _description_preview_from_job(job: Job) -> Optional[str]:
        raw_description = getattr(job, "description", None)
        if raw_description is None:
            return None

        plain_text = re.sub(r"<[^>]+>", " ", str(raw_description))
        plain_text = html.unescape(plain_text)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        if not plain_text:
            return None

        max_chars = CandidateJobSearchService.JOB_DESCRIPTION_PREVIEW_CHARS
        if len(plain_text) <= max_chars:
            return plain_text
        return plain_text[: max_chars - 3].rstrip() + "..."

    @staticmethod
    def _experience_required_from_job(job: Job) -> Optional[str]:
        min_exp = job.experience_min
        max_exp = job.experience_max
        if min_exp is None and max_exp is None:
            return None
        if min_exp is not None and max_exp is not None:
            return f"{min_exp}-{max_exp} Years"
        if min_exp is not None:
            return f"{min_exp}+ Years"
        return f"Up to {max_exp} Years"

    @staticmethod
    def _salary_range_from_job(job: Job) -> Optional[str]:
        if job.salary_min is None and job.salary_max is None:
            return None
        if job.salary_min is not None and job.salary_max is not None:
            return f"{job.salary_min} - {job.salary_max}"
        if job.salary_min is not None:
            return f"{job.salary_min}+"
        return f"Up to {job.salary_max}"

    @staticmethod
    def _job_card_from_job(
        job: Job,
        *,
        logo: Optional[str] = None,
        is_saved: bool = False,
        application=None,
    ) -> CandidateJobCardResponse:
        return CandidateJobCardResponse(
            job_id=job.job_id,
            job_title=job.title,
            job_slug=slugify_job_title(job.title),
            description_preview=CandidateJobSearchService._description_preview_from_job(job),
            company_name=job.company_name,
            company_logo=logo,
            location=job.location,
            salary_range=CandidateJobSearchService._salary_range_from_job(job),
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            employment_type=job.employment_type,
            work_preference=job.work_mode,
            experience_required=CandidateJobSearchService._experience_required_from_job(job),
            posted_date=job.created_at,
            skills=[s.skill for s in (job.skills or [])],
            is_saved=is_saved,
            already_applied=application is not None,
            application_status=application.application_status if application else None,
        )

    @staticmethod
    def _company_info_from_profile(company) -> Optional[CandidateCompanyInfoResponse]:
        if not company:
            return None
        return CandidateCompanyInfoResponse(
            company_id=getattr(company, "company_id", None),
            company_name=getattr(company, "company_name", None),
            website=getattr(company, "website", None),
            logo_url=getattr(company, "logo_url", None),
            logo_path=getattr(company, "logo_path", None),
            description=getattr(company, "description", None),
            industry=getattr(company, "industry", None),
            size=getattr(company, "company_size", None) or getattr(company, "size", None),
            founded_year=getattr(company, "founded_year", None),
            location=getattr(company, "location", None),
            headquarters_country=getattr(company, "headquarters_country", None),
            headquarters_state=getattr(company, "headquarters_state", None),
            headquarters_city=getattr(company, "headquarters_city", None),
            verification_status=getattr(company, "verification_status", None),
        )

    @staticmethod
    def _recruiter_public_info_from_profile(recruiter) -> Optional[CandidateRecruiterPublicInfoResponse]:
        if not recruiter:
            return None
        return CandidateRecruiterPublicInfoResponse(
            recruiter_id=getattr(recruiter, "id", None),
            job_title=getattr(recruiter, "job_title", None),
            department=getattr(recruiter, "department", None),
            bio=getattr(recruiter, "bio", None),
            location=getattr(recruiter, "location", None),
            linkedin_url=getattr(recruiter, "linkedin_url", None),
            profile_photo=getattr(recruiter, "profile_photo", None),
            candidate_response_time=getattr(recruiter, "candidate_response_time", None),
            interview_mode=getattr(recruiter, "interview_mode", None),
            languages=list(getattr(recruiter, "languages", None) or []),
        )

    @staticmethod
    async def search_jobs(
        session: AsyncSession,
        user_id: Optional[UUID] = None,
        *,
        search: Optional[str] = None,
        location: Optional[str] = None,
        work_preference: Optional[str] = None,
        employment_type: Optional[str] = None,
        experience_level: Optional[str] = None,
        candidate_experience: Optional[int] = None,
        salary_min: Optional[float] = None,


        salary_max: Optional[float] = None,
        skills: Optional[List[str]] = None,
        posted_within: Optional[str] = None,
        company: Optional[str] = None,
        sort: str = "Relevance",
        page: int = 1,
        page_size: int = 20,
    ) -> CandidateJobSearchResponse:

        total, jobs = await CandidateJobSearchRepo.get_job_card_search(
            session,
            user_id,
            search=search,
            location=location,
            work_preference=work_preference,
            employment_type=employment_type,
            experience_level=experience_level,
            candidate_experience=candidate_experience,
            salary_min=salary_min,



            salary_max=salary_max,
            skills=skills,
            posted_within=posted_within,
            company=company,
            sort=sort,
            page=page,
            page_size=page_size,
        )

        job_ids = [j.job_id for j in jobs]

        if user_id:
            saved_job_ids, apps_map = await CandidateJobSearchRepo.get_saved_and_applied_maps(
                session,
                user_id,
                job_ids,
            )
        else:
            saved_job_ids = set()
            apps_map = {}

        logo_map = await CandidateJobSearchRepo.get_company_logo_path_for_jobs(
            session,
            job_ids,
        )

        results = []
        for j in jobs:
            app = apps_map.get(j.job_id)

            results.append(
                CandidateJobSearchService._job_card_from_job(
                    j,
                    logo=logo_map.get(j.job_id),
                    is_saved=j.job_id in saved_job_ids,
                    application=app,
                )
            )

        return CandidateJobSearchResponse(
            total_records=total,
            page=page,
            page_size=page_size,
            results=results,
        )

    @staticmethod
    async def get_job_details(
        session: AsyncSession,
        user_id: Optional[UUID] = None,
        job_id: str = "",
    ) -> Optional[CandidateJobDetailsResponse]:

        job = await CandidateJobSearchRepo.get_job_details(
            session,
            user_id,
            job_id,
        )

        if not job:
            return None

        if user_id:
            saved_job_ids, apps_map = await CandidateJobSearchRepo.get_saved_and_applied_maps(
                session,
                user_id,
                [job.job_id],
            )
        else:
            saved_job_ids = set()
            apps_map = {}

        logo_map = await CandidateJobSearchRepo.get_company_logo_path_for_jobs(
            session,
            [job.job_id],
        )
        company_map = await CandidateJobSearchRepo.get_company_profiles_for_jobs(
            session,
            [job.job_id],
        )
        recruiter_map = await CandidateJobSearchRepo.get_public_recruiter_profiles_for_jobs(
            session,
            [job.job_id],
        )

        app = apps_map.get(job.job_id)
        skills = [s.skill for s in (job.skills or [])]

        return CandidateJobDetailsResponse(
            job_id=job.job_id,
            job_title=job.title,
            job_slug=slugify_job_title(job.title),

            company_name=job.company_name,
            company_logo=logo_map.get(job.job_id),
            location=job.location,
            country_id=job.country_id,
            location_id=job.location_id,
            custom_city=job.custom_city,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_range=CandidateJobSearchService._salary_range_from_job(job),
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            employment_type=job.employment_type,
            work_preference=job.work_mode,
            workplace_type=job.work_mode,
            experience_required=CandidateJobSearchService._experience_required_from_job(job),
            experience_min=job.experience_min,
            experience_max=job.experience_max,
            job_category=job.job_category,
            seniority_level=job.seniority_level,
            team=job.team,
            team_size=job.team_size,
            education=job.education,
            job_description=job.description,
            responsibilities=list(job.responsibilities or []),
            requirements=list(job.requirements or []),
            required_skills=skills,
            preferred_skills=[],
            benefits=list(job.benefits or []),
            application_instructions=job.application_instructions,
            working_hours=job.working_hours,
            office_location=job.office_location,
            map_url=job.map_url,
            skills=skills,
            posted_date=job.created_at,
            updated_date=job.updated_at,
            application_deadline=job.application_deadline,
            number_of_openings=job.no_of_openings,
            job_status=job.status,
            company_info=CandidateJobSearchService._company_info_from_profile(
                company_map.get(job.job_id)
            ),
            recruiter_public_info=CandidateJobSearchService._recruiter_public_info_from_profile(
                recruiter_map.get(job.job_id)
            ),
            is_saved=job.job_id in saved_job_ids,
            already_applied=app is not None,
            application_status=app.application_status if app else None,
            recommended_jobs=[],
        )

    @staticmethod
    async def get_suggestions(
        session: AsyncSession,
        q: str,
        user_id: Optional[UUID] = None,
        limit: int = 8,
    ) -> CandidateJobSuggestionsResponse:

        did_you_mean, suggestions, jobs = await CandidateJobSearchRepo.get_suggestions(
            session,
            user_id=user_id,
            q=q,
            limit=limit,
        )
        job_ids = [j.job_id for j in jobs]
        if user_id:
            saved_job_ids, apps_map = await CandidateJobSearchRepo.get_saved_and_applied_maps(
                session,
                user_id,
                job_ids,
            )
        else:
            saved_job_ids = set()
            apps_map = {}

        logo_map = await CandidateJobSearchRepo.get_company_logo_path_for_jobs(
            session,
            job_ids,
        )

        return CandidateJobSuggestionsResponse(
            query=q,
            did_you_mean=did_you_mean,
            suggestions=suggestions,
            jobs=[
                CandidateJobSearchService._job_card_from_job(
                    job,
                    logo=logo_map.get(job.job_id),
                    is_saved=job.job_id in saved_job_ids,
                    application=apps_map.get(job.job_id),
                )
                for job in jobs
            ],
        )
