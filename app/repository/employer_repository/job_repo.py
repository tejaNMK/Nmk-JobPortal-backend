from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional, Sequence, Tuple
from app.utils.utc import utc_now_naive

from app.schema.job import JobListFiltersSchema

from fastapi import HTTPException

from sqlalchemy import Date, cast, delete, func, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback

from app.model.employer_model.job import Job
from app.model.employer_model.job_posting_audit import JobPostingAudit
from app.model.employer_model.job_skill import JobSkill

from app.service.employer_service.job_idempotency_errors import (
    DuplicateJobIdempotencyKeyError,
    DuplicateJobPostingError,
)
from app.utils.job_time import normalize_deadline_to_utc_naive, utc_now_naive



_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_WHITESPACE_RE = re.compile(r"\s+")
JOB_DUPLICATE_UNIQUE_INDEX = "idx_jobs_unique_active_posting"
JOB_IDEMPOTENCY_UNIQUE_INDEX = "idx_jobs_employer_idempotency"
JOB_STATUSES = {"DRAFT", "PUBLISHED", "CLOSED", "EXPIRED"}
OPEN_JOB_STATUSES = {"PUBLISHED"}
DUPLICATE_JOB_MESSAGE = (
    "Duplicate job posting detected. "
    "A job with the same title, company, location, employment type and posted date already exists."
)
DUPLICATE_JOB_AUDIT_EVENT = "DUPLICATE_JOB_ATTEMPT"


def _canonical_job_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = str(status).strip().upper().replace("-", "_").replace(" ", "_")
    if normalized not in JOB_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid job status")
    return normalized


def _parse_single_or_range(raw: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not raw or not str(raw).strip():
        return None, None
    v = str(raw).strip()
    m = _RANGE_RE.match(v)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            return None, None
        return a, b
    if v.isdigit():
        return int(v), int(v)
    return None, None


def normalize_job_duplicate_text(value: Optional[str]) -> str:

    return _WHITESPACE_RE.sub(" ", str(value or "").strip()).lower()


def _normalized_sql_value(column):
    return func.lower(
        func.regexp_replace(
            func.trim(func.coalesce(column, "")),
            r"\s+",
            " ",
            "g",
        )
    )


def _integrity_constraint_name(exc: IntegrityError) -> Optional[str]:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None) if orig is not None else None
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name:
        return str(constraint_name)

    message = str(orig or exc)
    for index_name in (JOB_IDEMPOTENCY_UNIQUE_INDEX, JOB_DUPLICATE_UNIQUE_INDEX):
        if index_name in message:
            return index_name
    return None


class JobRepository:
    OPEN_STATUSES = OPEN_JOB_STATUSES

    @staticmethod
    async def expire_jobs_past_deadline(
        *,
        session: AsyncSession,
        now: Optional[datetime] = None,
        employer_id: Optional[str] = None,
    ) -> int:
        now_utc = now or utc_now_naive()
        if now_utc.tzinfo is not None:
            now_utc = now_utc.astimezone(timezone.utc).replace(tzinfo=None)

        conditions = [
            Job.status.in_(OPEN_JOB_STATUSES),
            Job.is_deleted == False,
            Job.closed_at.is_(None),
            Job.application_deadline.isnot(None),
            Job.application_deadline < now_utc,
        ]
        if employer_id:
            conditions.append(Job.employer_id == employer_id)

        result = await session.execute(
            update(Job)
            .where(*conditions)
            .values(
                status="EXPIRED",
                updated_at=now_utc,
                updated_by="system:deadline-expiry",
            )
            .execution_options(synchronize_session="fetch")
        )
        changed = int(result.rowcount or 0)
        if changed:
            await commit_rollback(session)
        return changed

    @staticmethod
    async def get_job_by_id(*, session: AsyncSession, job_id: str) -> Optional[Job]:
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(Job.job_id == job_id, Job.is_deleted == False)
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_job(
        job_id: str,
        employer_id: str,
        db: AsyncSession,
        actor_user_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        commit: bool = True,
    ) -> bool:
        q = select(Job).where(Job.job_id == job_id, Job.is_deleted == False)

        try:
            result = await db.execute(q)
            job = result.scalar_one_or_none()
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found.")

            if job.employer_id != employer_id:
                raise HTTPException(
                    status_code=403,
                    detail="You are not authorized to delete this job.",
                )

            now = utc_now_naive()
            previous_status = job.status
            job.is_deleted = True
            job.deleted_at = now
            job.updated_at = now
            job.updated_by = actor_user_id
            if job.status in OPEN_JOB_STATUSES:
                job.status = "CLOSED"
                job.closed_at = job.closed_at or now
                job.closed_reason = job.closed_reason or "Deleted by employer"

            db.add(
                JobPostingAudit(
                    employer_id=employer_id,
                    job_id=job.job_id,
                    event_type="JOB_DELETED",
                    message=(
                        f"deleted_job_id={job.job_id}; title={job.title}; "
                        f"previous_status={previous_status}; new_status={job.status}; "
                        f"timestamp={now.isoformat()}"
                    ),
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    created_at=now,
                )
            )

            if commit:
                await db.commit()
            else:
                await db.flush()
            return True
        except HTTPException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_job_by_idempotency_key(
        *,
        session: AsyncSession,
        employer_id: str,
        idempotency_key: str,
    ) -> Optional[Job]:
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(
                Job.employer_id == employer_id,
                Job.idempotency_key == idempotency_key,
                Job.is_deleted == False,
            )
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def find_duplicate_active_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_title: str,
        company_name: str,
        location: str,
        employment_type: str,
        posted_date: date,
    ) -> Optional[Job]:
        q = (
            select(Job)
            .where(
                Job.employer_id == employer_id,
                _normalized_sql_value(Job.title) == normalize_job_duplicate_text(job_title),
                _normalized_sql_value(Job.company_name) == normalize_job_duplicate_text(company_name),
                _normalized_sql_value(Job.location) == normalize_job_duplicate_text(location),
                _normalized_sql_value(Job.employment_type) == normalize_job_duplicate_text(employment_type),
                cast(Job.created_at, Date) == posted_date,
                Job.status.in_(OPEN_JOB_STATUSES),
                Job.is_deleted == False,
            )
            .limit(1)
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_published_jobs(
        *,
        session: AsyncSession,
        employer_id: str,
    ) -> int:
        result = await session.execute(
            select(func.count(Job.job_id)).where(
                Job.employer_id == employer_id,
                Job.status.in_(OPEN_JOB_STATUSES),
                Job.is_deleted == False,
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def log_duplicate_job_attempt(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: Optional[str],
        title: str,
        company_name: str,
        location: str,
        employment_type: str,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
        request_id: Optional[str],
    ) -> None:
        now = utc_now_naive()
        message_parts = [
            f"recruiter_id={actor_user_id or ''}",
            f"title={normalize_job_duplicate_text(title)}",
            f"company={normalize_job_duplicate_text(company_name)}",
            f"location={normalize_job_duplicate_text(location)}",
            f"employment_type={normalize_job_duplicate_text(employment_type)}",
            f"timestamp={now.isoformat()}",
        ]
        if request_id:
            message_parts.append(f"request_id={request_id}")

        session.add(
            JobPostingAudit(
                employer_id=employer_id,
                job_id=job_id or "",
                event_type=DUPLICATE_JOB_AUDIT_EVENT,
                message="; ".join(message_parts),
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                created_at=now,
            )
        )
        await commit_rollback(session)

    @staticmethod
    async def list_employer_jobs(
        *,
        session: AsyncSession,
        employer_id: str,
        filters: JobListFiltersSchema,
    ) -> tuple[list[Job], int]:
       

       
        conditions = [
            Job.employer_id == employer_id,
            Job.is_deleted == False,
        ]

        if filters.search:
            conditions.append(Job.title.ilike(f"%{filters.search}%"))

        if filters.location:
            conditions.append(Job.location.ilike(f"%{filters.location}%"))

        if filters.employment_type:
            conditions.append(Job.employment_type.ilike(f"%{filters.employment_type}%"))

        # Experience keyword/range filter
        # Supported inputs: "FRESHER", "1-3", "3-5", "5+", "2"
        if filters.experience:
            exp_raw = str(filters.experience).strip().upper()
            exp_min = None
            exp_max = None
            if exp_raw == "FRESHER":
                exp_min, exp_max = 0, 0
            elif exp_raw.endswith("+") and exp_raw[:-1].isdigit():
                exp_min = int(exp_raw[:-1])
                exp_max = None
            else:
                exp_min, exp_max = _parse_single_or_range(filters.experience)

            if exp_min is not None or exp_max is not None:
                if exp_min is not None and exp_max is not None:
                    # Overlap between requested range and stored range
                    conditions.append(
                        (Job.experience_max.isnot(None)) &
                        (Job.experience_min <= exp_max) &
                        (Job.experience_max >= exp_min)
                    )
                elif exp_min is not None and exp_max is None:
                    # "X+" requested behaves like: exp_min <= N and stored overlaps
                    # For numeric N: return jobs where experience_min <= N <= experience_max
                    # With stored_max >= exp_min and stored_min <= exp_min is equivalent to overlap.
                    conditions.append(
                        (Job.experience_min <= exp_min) &
                        (Job.experience_max.isnot(None)) &
                        (Job.experience_max >= exp_min)
                    )

                elif exp_max is not None and exp_min is None:
                    # Single-sided range: overlap with [0, exp_max]
                    conditions.append(
                        (Job.experience_max.isnot(None)) &
                        (Job.experience_min <= exp_max) &
                        (Job.experience_max >= exp_max)
                    )



        # Sort mapping
        sort_key = filters.sort_by
        if sort_key == "POSTED_DATE_ASC":
            order_by = Job.created_at.asc()
        elif sort_key == "JOB_TITLE_ASC":
            order_by = Job.title.asc()
        elif sort_key == "JOB_TITLE_DESC":
            order_by = Job.title.desc()
        elif sort_key == "LOCATION_ASC":
            order_by = Job.location.asc()
        elif sort_key == "LOCATION_DESC":
            order_by = Job.location.desc()
        else:
            # Default: POSTED_DATE_DESC
            order_by = Job.created_at.desc()

        page = filters.page
        page_size = filters.page_size
        offset_val = (page - 1) * page_size

        where_clause = conditions[0]
        for c in conditions[1:]:
            where_clause = where_clause & c

        # total
        count_q = select(Job.job_id).where(where_clause)
        count_q = count_q.order_by(None)
        total_records = (await session.execute(count_q)).all()
        total = len(total_records)

        # rows
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(where_clause)
            .order_by(order_by)
            .limit(page_size)
            .offset(offset_val)
        )
        result = await session.execute(q)
        rows = list(result.scalars().all())
        return rows, total

    @staticmethod
    async def get_job_for_employer(*, session: AsyncSession, employer_id: str, job_id: str) -> Optional[Job]:
        q = select(Job).options(selectinload(Job.skills)).where(Job.employer_id == employer_id, Job.job_id == job_id, Job.is_deleted == False)
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def close_job(
        *,
        session: AsyncSession,
        job_id: str,
        employer_id: str,
        reason: Optional[str],
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Optional[Job]:
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(
                Job.job_id == job_id,
                Job.employer_id == employer_id,
                Job.is_deleted == False,
            )
        )
        result = await session.execute(q)
        job = result.scalar_one_or_none()
        if job is None:
            return None

        previous_status = job.status
        now = utc_now_naive()
        job.status = "CLOSED"
        job.closed_at = now
        job.closed_reason = reason
        job.updated_at = now
        job.updated_by = actor_user_id

        audit = JobPostingAudit(
            employer_id=employer_id,
            job_id=job.job_id,
            event_type="JOB_CLOSED",
            message=(
                f"previous_status={previous_status}; new_status=CLOSED; "
                f"reason={reason or ''}; timestamp={now.isoformat()}"
            ),
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        session.add(audit)

        await commit_rollback(session)
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(Job.job_id == job.job_id, Job.is_deleted == False)
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
        update_data: dict,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Optional[Job]:
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(
                Job.employer_id == employer_id,
                Job.job_id == job_id,
                Job.is_deleted == False,
            )
        )
        result = await session.execute(q)
        job: Optional[Job] = result.scalar_one_or_none()
        if job is None:
            return None

        # Update only provided keys
        if "job_title" in update_data:
            job.title = update_data["job_title"]

        if "job_description" in update_data:
            job.description = update_data["job_description"]

        if "employment_type" in update_data:
            job.employment_type = update_data["employment_type"]
        if "experience_required" in update_data:
            experience_min, experience_max = _parse_single_or_range(update_data["experience_required"])
            job.experience_min = experience_min
            job.experience_max = experience_max
        if "location" in update_data:
            job.location = update_data["location"]
        if "country_id" in update_data:
            job.country_id = update_data["country_id"]
        if "location_id" in update_data:
            job.location_id = update_data["location_id"]
        if "custom_city" in update_data:
            job.custom_city = update_data["custom_city"]
        if "work_mode" in update_data:
            job.work_mode = update_data["work_mode"]
        if "salary_range" in update_data:
            salary_min, salary_max = _parse_single_or_range(update_data["salary_range"])
            job.salary_min = float(salary_min) if salary_min is not None else None
            job.salary_max = float(salary_max) if salary_max is not None else None
        if "salary_currency" in update_data:
            job.salary_currency = update_data["salary_currency"]
        if "salary_period" in update_data:
            job.salary_period = update_data["salary_period"]
        if "number_of_openings" in update_data:
            job.no_of_openings = update_data["number_of_openings"]
        if "application_deadline" in update_data:
            application_deadline = update_data["application_deadline"]
            application_deadline = normalize_deadline_to_utc_naive(application_deadline)
            job.application_deadline = application_deadline
        if "company_name" in update_data:
            job.company_name = update_data["company_name"]
        if "contact_email" in update_data:
            job.contact_email = update_data["contact_email"]
        if "job_category" in update_data:
            job.job_category = update_data["job_category"]
        if "seniority_level" in update_data:
            job.seniority_level = update_data["seniority_level"]
        if "team" in update_data:
            job.team = update_data["team"]
        if "team_size" in update_data:
            job.team_size = update_data["team_size"]
        if "education" in update_data:
            job.education = update_data["education"]
        if "responsibilities" in update_data:
            job.responsibilities = list(update_data["responsibilities"] or [])
        if "requirements" in update_data:
            job.requirements = list(update_data["requirements"] or [])
        if "benefits" in update_data:
            job.benefits = list(update_data["benefits"] or [])
        if "application_instructions" in update_data:
            job.application_instructions = update_data["application_instructions"]
        if "working_hours" in update_data:
            job.working_hours = update_data["working_hours"]
        if "office_location" in update_data:
            job.office_location = update_data["office_location"]
        if "map_url" in update_data:
            job.map_url = update_data["map_url"]
        if "status" in update_data:
            job.status = _canonical_job_status(update_data["status"])

        now = utc_now_naive()
        if (
            job.status in OPEN_JOB_STATUSES
            and job.application_deadline is not None
            and job.application_deadline < now
        ):
            raise HTTPException(
                status_code=400,
                detail="Application deadline cannot be in the past",
            )

        # Relationship updates (skills)
        if "skills" in update_data:
            await session.execute(select(JobSkill).where(JobSkill.job_id == job.job_id))
            await session.execute(delete(JobSkill).where(JobSkill.job_id == job.job_id))
            for skill in update_data["skills"]:
                session.add(JobSkill(job_id=job.job_id, skill=skill))

        audit = JobPostingAudit(
            employer_id=employer_id,
            job_id=job.job_id,
            event_type="JOB_UPDATED",
            message="Job updated successfully",
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        session.add(audit)

        await commit_rollback(session)
        q = (
            select(Job)
            .options(selectinload(Job.skills))
            .where(Job.job_id == job.job_id, Job.is_deleted == False)
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()



    @staticmethod
    async def create_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_title: str,
        job_description: str,
        employment_type: str,
        experience_required: str,
        location: Optional[str],
        country_id: Optional[str],
        location_id: Optional[str],
        custom_city: Optional[str],
        work_mode: str,
        salary_range: Optional[str],
        salary_currency: Optional[str],
        salary_period: Optional[str],
        number_of_openings: int,
        application_deadline: Optional[datetime],
        company_name: str,
        contact_email: str,
        job_category: Optional[str],
        seniority_level: Optional[str],
        team: Optional[str],
        team_size: Optional[str],
        education: Optional[str],
        responsibilities: Optional[Sequence[str]],
        requirements: Optional[Sequence[str]],
        benefits: Optional[Sequence[str]],
        application_instructions: Optional[str],
        working_hours: Optional[str],
        office_location: Optional[str],
        map_url: Optional[str],
        status: str,
        skills: Sequence[str],
        idempotency_key: Optional[str],
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Job:
        experience_min, experience_max = _parse_single_or_range(experience_required)
        salary_min, salary_max = (
            _parse_single_or_range(salary_range) if salary_range else (None, None)
        )
        application_deadline = normalize_deadline_to_utc_naive(application_deadline)

        job = Job(
            employer_id=employer_id,
            title=job_title,
            description=job_description,
            employment_type=employment_type,
            experience_min=experience_min,
            experience_max=experience_max,
            location=location,
            country_id=country_id,
            location_id=location_id,
            custom_city=custom_city,
            work_mode=work_mode,
            salary_min=float(salary_min) if salary_min is not None else None,
            salary_max=float(salary_max) if salary_max is not None else None,
            salary_currency=salary_currency or "USD",
            salary_period=salary_period or "Monthly",
            no_of_openings=number_of_openings,
            application_deadline=application_deadline,
            status=_canonical_job_status(status) or "DRAFT",
            company_name=company_name,
            contact_email=contact_email,
            job_category=job_category,
            seniority_level=seniority_level,
            team=team,
            team_size=team_size,
            education=education,
            responsibilities=list(responsibilities or []),
            requirements=list(requirements or []),
            benefits=list(benefits or []),
            application_instructions=application_instructions,
            working_hours=working_hours,
            office_location=office_location,
            map_url=map_url,
            idempotency_key=idempotency_key,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        session.add(job)

        try:
            await session.flush()

            for skill in skills:
                session.add(JobSkill(job_id=job.job_id, skill=skill))

            audit = JobPostingAudit(
                employer_id=employer_id,
                job_id=job.job_id,
                event_type="JOB_CREATED",
                message="Job created successfully",
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
            session.add(audit)

            await commit_rollback(session)
            q = (
                select(Job)
                .options(selectinload(Job.skills))
                .where(Job.job_id == job.job_id, Job.is_deleted == False)
            )
            result = await session.execute(q)
            return result.scalar_one_or_none()

        except IntegrityError as exc:
            await session.rollback()

            constraint_name = _integrity_constraint_name(exc)

            if constraint_name == JOB_IDEMPOTENCY_UNIQUE_INDEX:
                raise DuplicateJobIdempotencyKeyError(
                    employer_id=employer_id,
                    idempotency_key=str(idempotency_key),
                ) from exc
            if constraint_name == JOB_DUPLICATE_UNIQUE_INDEX:
                raise DuplicateJobPostingError(employer_id=employer_id) from exc

            raise HTTPException(
                status_code=400,
                detail="Job could not be created",
            ) from exc


