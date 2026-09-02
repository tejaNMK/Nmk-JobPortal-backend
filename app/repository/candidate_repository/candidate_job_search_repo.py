from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID
from sqlalchemy import and_, func, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
from app.model.employer_model.job import Job
from app.repository.employer_repository.job_repo import JobRepository


class CandidateJobSearchRepo:
    _WORK_PREFERENCE_QUERY_CANONICAL = {
        "REMOTE": "REMOTE",
        "REMOTE_WORK": "REMOTE",
        "REMOTEWORK": "REMOTE",
        "REMOTE_WORK": "REMOTE",
        "ONSITE": "ONSITE",
        "ON_SITE": "ONSITE",
        "ON_SITEWORK": "ONSITE",
        "ON_SITE_WORK": "ONSITE",
        "HYBRID": "HYBRID",
    }

    _EMPLOYMENT_TYPE_QUERY_CANONICAL = {
        "FULL_TIME": "FULL_TIME",
        "FULLTIME": "FULL_TIME",
        "PART_TIME": "PART_TIME",
        "PARTTIME": "PART_TIME",
        "CONTRACT": "CONTRACT",
        "INTERNSHIP": "INTERNSHIP",
    }


    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def open_statuses() -> tuple[str, ...]:
        return ("PUBLISHED",)

    @staticmethod
    def _active_job_predicate(now: datetime):
        return and_(
            Job.status.in_(CandidateJobSearchRepo.open_statuses()),
            Job.is_deleted.is_(False),
            Job.closed_at.is_(None),
            or_(Job.application_deadline.is_(None), Job.application_deadline >= now),
        )

    @staticmethod
    def _normalize_skills(skills: Optional[Sequence[str]]) -> Optional[List[str]]:
        if not skills:
            return None
        out: list[str] = []
        for s in skills:
            if s is None:
                continue
            s2 = str(s).strip()
            if s2:
                out.append(s2)
        return out or None

    @staticmethod
    def _normalize_work_preference_for_query(raw: Optional[str]) -> Optional[str]:
        if raw is None:
            return None

        value = str(raw).strip()
        if not value:
            return None

        normalized = value.upper().replace("-", "_").replace(" ", "_")
        return CandidateJobSearchRepo._WORK_PREFERENCE_QUERY_CANONICAL.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _normalize_employment_type_for_query(raw: Optional[str]) -> Optional[str]:
        if raw is None:
            return None

        value = str(raw).strip()
        if not value:
            return None

        normalized = value.upper().replace("-", "_").replace(" ", "_")
        return CandidateJobSearchRepo._EMPLOYMENT_TYPE_QUERY_CANONICAL.get(
            normalized,
            normalized,
        )

    @classmethod
    async def _get_candidate_id(cls, session: AsyncSession, user_id) -> Optional[str]:
       
        from app.model.candidate_model.candidate_profile import CandidateProfile

        result = await session.execute(
            select(CandidateProfile.candidate_id).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_job_card_search(
        cls,
        session: AsyncSession,
        user_id,
        *,
        search: Optional[str] = None,
        location: Optional[str] = None,
        work_preference: Optional[str] = None,
        employment_type: Optional[str] = None,
        experience_level: Optional[str] = None,
        candidate_experience: Optional[int] = None,

        salary_min: Optional[float] = None,

        salary_max: Optional[float] = None,
        skills: Optional[Sequence[str]] = None,
        posted_within: Optional[str] = None,
        company: Optional[str] = None,
        sort: str = "Relevance",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[int, List[Job]]:
        now = cls._utc_now_naive()
        await JobRepository.expire_jobs_past_deadline(session=session, now=now)
        skills_norm = cls._normalize_skills(skills)

        # Experience filtering is dynamic (numeric) using DB range.
        # candidate_experience is the preferred numeric API.
        candidate_experience_value: Optional[int] = candidate_experience

        # Backward compatibility: if only legacy label is present, translate to a representative numeric value.
        # Repository filtering remains numeric min/max comparisons.
        if candidate_experience_value is None and experience_level:
            legacy_mapping = {
                "Fresher": 0,
                "1-3 Years": 1,
                "3-5 Years": 3,
                "5+ Years": 5,
            }
            candidate_experience_value = legacy_mapping.get(experience_level)

        conditions = [cls._active_job_predicate(now)]

        normalized_work_preference = cls._normalize_work_preference_for_query(work_preference)
        normalized_employment_type = cls._normalize_employment_type_for_query(employment_type)

        if search:
            st = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Job.title.ilike(st),
                    Job.description.ilike(st),
                    Job.company_name.ilike(st),
                    Job.location.ilike(st),
                )
            )

        if location:
            conditions.append(Job.location.ilike(f"%{location.strip()}%"))

        if company:
            conditions.append(Job.company_name.ilike(f"%{company.strip()}%"))

        if normalized_work_preference:
            conditions.append(Job.work_mode == normalized_work_preference)

        if normalized_employment_type:
            conditions.append(Job.employment_type == normalized_employment_type)

        if candidate_experience_value is not None:
            conditions.append(Job.experience_min <= candidate_experience_value)
            conditions.append(
                or_(
                    Job.experience_max.is_(None),
                    candidate_experience_value <= Job.experience_max,
                )
            )





        if salary_min is not None:
            conditions.append(or_(Job.salary_max.is_(None), Job.salary_max >= salary_min))

        if salary_max is not None:
            conditions.append(or_(Job.salary_min.is_(None), Job.salary_min <= salary_max))

        if skills_norm:
            from app.model.employer_model.job_skill import JobSkill

            st = [s.lower() for s in skills_norm]
            conditions.append(
                Job.job_id.in_(
                    select(JobSkill.job_id).where(func.lower(JobSkill.skill).in_(st))
                )
            )

        if posted_within:
            delta = {
                "24h": timedelta(days=1),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
            }.get(posted_within)
            if delta:
                conditions.append(Job.created_at >= now - delta)

        base = (
            select(Job)
            .where(*conditions)
            .options(selectinload(Job.skills))
        )

        if sort == "Newest":
            order_by = [Job.created_at.desc()]
        else:
            order_by = [Job.created_at.desc()]
            if search:
                st = search.strip()
                pattern = f"%{st}%"

                order_by = [
                    case(
                        (func.lower(func.trim(Job.title)) == func.lower(st.strip()), 3),
                        else_=0,
                    ).desc(),
                    case(
                        (Job.title.ilike(pattern), 2),
                        else_=0,
                    ).desc(),
                    case(
                        (Job.company_name.ilike(pattern), 1),
                        else_=0,
                    ).desc(),
                    Job.created_at.desc(),
                ]

        count_q = select(func.count()).select_from(base.subquery())
        total = int((await session.execute(count_q)).scalar_one() or 0)

        paged = base.order_by(*order_by).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(paged)).scalars().all()
        return total, rows

    @classmethod
    async def _get_saved_job_ids(cls, session: AsyncSession, candidate_id: str) -> set[str]:
        result = await session.execute(
            select(CandidateSavedJob.job_id).where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.saved_flag.is_(True),
                CandidateSavedJob.deleted_at.is_(None),
            )
        )
        return set(result.scalars().all())

    @classmethod
    async def _get_applications_for_jobs(
        cls, session: AsyncSession, candidate_id: str, job_ids: Iterable[str]
    ) -> Dict[str, JobApplication]:
        job_ids_list = list(job_ids)
        if not job_ids_list:
            return {}

        result = await session.execute(
            select(JobApplication).where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.job_id.in_(job_ids_list),
                JobApplication.is_deleted.is_(False),
            )
        )
        apps = result.scalars().all()
        return {a.job_id: a for a in apps}

    @classmethod
    async def get_job_details(
        cls, session: AsyncSession, user_id: Optional[UUID], job_id: str
    ) -> Optional[Job]:
        now = cls._utc_now_naive()
        await JobRepository.expire_jobs_past_deadline(session=session, now=now)

        q = (
            select(Job)
            .where(
                Job.job_id == job_id,
                cls._active_job_predicate(now),
            )
            .options(selectinload(Job.skills))
        )

        job = (await session.execute(q)).scalar_one_or_none()
        return job

    @classmethod
    async def get_saved_and_applied_maps(
        cls,
        session: AsyncSession,
        user_id: Optional[UUID],
        job_ids: Iterable[str],
    ) -> Tuple[set[str], Dict[str, JobApplication]]:

        if not user_id:
            return set(), {}

        candidate_id = await cls._get_candidate_id(session, user_id)
        if not candidate_id:
            return set(), {}

        saved_job_ids = await cls._get_saved_job_ids(session, candidate_id)
        apps_map = await cls._get_applications_for_jobs(
            session,
            candidate_id,
            job_ids,
        )

        return saved_job_ids, apps_map

    @classmethod
    async def get_company_logo_path_for_jobs(
        cls, session: AsyncSession, job_ids: Iterable[str]
    ) -> Dict[str, Optional[str]]:
        job_ids_list = list(job_ids)
        if not job_ids_list:
            return {}

        from app.model.employer_model.company_profile import CompanyProfile

        # Jobs already contain company_name, but logo is on CompanyProfile.
        # Join by employer_id.
        from app.model.employer_model.job import Job as JobModel

        result = await session.execute(
            select(JobModel.job_id, CompanyProfile.logo_path).join(
                CompanyProfile, CompanyProfile.employer_id == JobModel.employer_id
            ).where(JobModel.job_id.in_(job_ids_list))
        )
        return {job_id: logo for job_id, logo in result.all()}

    @classmethod
    async def get_company_profiles_for_jobs(
        cls, session: AsyncSession, job_ids: Iterable[str]
    ) -> Dict[str, object]:
        job_ids_list = list(job_ids)
        if not job_ids_list:
            return {}

        from app.model.employer_model.company_profile import CompanyProfile
        from app.model.employer_model.job import Job as JobModel

        result = await session.execute(
            select(JobModel.job_id, CompanyProfile)
            .join(CompanyProfile, CompanyProfile.employer_id == JobModel.employer_id)
            .where(
                JobModel.job_id.in_(job_ids_list),
                CompanyProfile.is_public.is_(True),
            )
        )
        return {job_id: company for job_id, company in result.all()}

    @classmethod
    async def get_public_recruiter_profiles_for_jobs(
        cls, session: AsyncSession, job_ids: Iterable[str]
    ) -> Dict[str, object]:
        job_ids_list = list(job_ids)
        if not job_ids_list:
            return {}

        from app.model.employer_model.employer_profile import EmployerProfile
        from app.model.employer_model.job import Job as JobModel

        result = await session.execute(
            select(JobModel.job_id, EmployerProfile)
            .join(EmployerProfile, EmployerProfile.id == JobModel.employer_id)
            .where(
                JobModel.job_id.in_(job_ids_list),
                EmployerProfile.visibility == "PUBLIC",
                EmployerProfile.status == "ACTIVE",
                EmployerProfile.is_deleted == 0,
            )
        )
        return {job_id: recruiter for job_id, recruiter in result.all()}

    @classmethod
    async def get_suggestions(
        cls,
        session: AsyncSession,
        *,
        user_id: Optional[UUID] = None,
        q: str,
        limit: int = 8,
    ) -> Tuple[Optional[str], List[str], List[Job]]:
        
        term = (q or "").strip()
        if not term:
            return None, [], []

        now = cls._utc_now_naive()
        await JobRepository.expire_jobs_past_deadline(session=session, now=now)
        base = (
            select(Job)
            .where(
                cls._active_job_predicate(now),
                Job.title.isnot(None),
            )
            .where(Job.title.ilike(f"%{term}%"))
            .options(selectinload(Job.skills))
            .limit(limit)
        )
        rows = (await session.execute(base)).scalars().all()
        unique = []
        seen = set()
        for job in rows:
            t = job.title
            if t not in seen:
                unique.append(t)
                seen.add(t)

        did_you_mean = unique[0] if unique else None
        return did_you_mean, unique, rows
