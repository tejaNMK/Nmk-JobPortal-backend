from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Sequence
from uuid import UUID
import logging

logger = logging.getLogger(__name__)
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job
from app.model.authentication.role import Role
from app.model.authentication.user_role import UsersRole
from app.repository.employer_repository.job_repo import DUPLICATE_JOB_MESSAGE, JobRepository
from app.repository.job_application_repo import JobApplicationRepo
from app.service.subscription.subscription_validator import SubscriptionValidator
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService

from app.schema.job import (
    CloseJobRequest,
    JobListFiltersSchema,
    JobListGridRowSchema,
    JobListResponseSchema,
    PostJobRequestSchema,
    UpdateJobRequestSchema,
)

from app.service.job_alert_notification_service import (
    JobAlertNotificationService,
)

from app.service.employer_service.job_idempotency_errors import (
    DuplicateJobIdempotencyKeyError,
    DuplicateJobPostingError,
)
from app.service.master_data_service import MasterDataService

from app.utils.slug import slugify_job_title
from app.utils.job_time import normalize_deadline_to_utc_naive, posted_display_date, utc_now_naive



def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _utc_now_naive() -> datetime:
    return utc_now_naive()


def _normalize_deadline_to_utc_naive(deadline: Optional[datetime]) -> Optional[datetime]:
    return normalize_deadline_to_utc_naive(deadline)


def _sanitize_job_description(description: str) -> str:
    if description is None:
        return ""
    return description.replace("\x00", "").strip()


def _job_audit_name(job) -> str:
    return (
        getattr(job, "title", None)
        or getattr(job, "job_title", None)
        or str(getattr(job, "job_id", "job"))
    )


def _validate_deadline(deadline: Optional[datetime]) -> None:
    if not deadline:
        return
    deadline_utc = _normalize_deadline_to_utc_naive(deadline)
    if deadline_utc < _utc_now_naive():
        raise HTTPException(status_code=400, detail="Application deadline cannot be in the past")


def _normalize_skills(skills: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for s in skills:
        if s is None:
            continue
        v = str(s).strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(v)
    return normalized


async def _resolve_job_location(
    *,
    session: AsyncSession,
    country_id: Optional[str],
    location_id: Optional[str],
    custom_city: Optional[str],
    fallback_location: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    if not country_id:
        if location_id or custom_city:
            raise HTTPException(status_code=400, detail="country_id is required when selecting or entering a city")
        return fallback_location, None, None, None

    country = await MasterDataService.validate_country(session, country_id)
    clean_custom_city = custom_city.strip() if custom_city else None

    if location_id and clean_custom_city:
        raise HTTPException(status_code=400, detail="Use either location_id or custom_city, not both")

    if location_id:
        location = await MasterDataService.validate_location_for_country(
            session,
            location_id,
            country_id,
        )
        return f"{location.name}, {country.name}", country.country_id, location.location_id, None

    if clean_custom_city:
        return f"{clean_custom_city}, {country.name}", country.country_id, None, clean_custom_city

    return fallback_location, country.country_id, None, None


class JobService:

    @staticmethod
    def _normalize_skills(skills: Sequence[str]) -> list[str]:
        return _normalize_skills(skills)

    @staticmethod
    async def _require_employer(
        session: AsyncSession,
        user_id: UUID,
    ) -> None:
        query = (
            select(Role.role_code)
            .join(UsersRole, UsersRole.role_id == Role.role_id)
            .where(
                UsersRole.user_id == user_id,
                UsersRole.active_flag == True,
            )
        )
        result = await session.execute(query)
        role_codes = {row[0] for row in result.all()}
        allowed = {"ROLE_RECRUITER", "ROLE_ADMIN"}
        if role_codes.isdisjoint(allowed):
            raise HTTPException(status_code=403, detail="Only admins, recruiters, and employers can create jobs")

    @staticmethod
    async def _ensure_published_job_limit_available(
        *,
        session: AsyncSession,
        user_id: UUID,
        employer_id: str,
    ) -> None:
        validator = SubscriptionValidator(
            session=session,
            user_id=user_id,
            role="EMPLOYER",
        )
        limit = await validator.get_limit("max_published_jobs")
        if limit is None:
            return

        current_count = await JobRepository.count_published_jobs(
            session=session,
            employer_id=employer_id,
        )
        if current_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"You can publish up to {limit} jobs with your current plan. "
                    "Close or expire an existing job, or upgrade your subscription."
                ),
            )

    @staticmethod
    async def _notify_matching_job_alerts_for_published_job(
        *,
        session: AsyncSession,
        job: Job,
    ) -> None:
        if str(getattr(job, "status", "")).upper() not in JobRepository.OPEN_STATUSES:
            return
        try:
            await JobAlertNotificationService.notify_matching_candidates(
                session=session,
                job=job,
            )
        except Exception:
            logger.exception(
                "Failed to send job alert notifications.",
                extra={
                    "job_id": getattr(job, "job_id", None),
                },
            )

    @staticmethod
    async def get_job_for_employer(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
    ) -> Job: 

        job = await JobRepository.get_job_for_employer(
            session=session,
            employer_id=employer_id,
            job_id=job_id,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        await JobRepository.expire_jobs_past_deadline(
            session=session,
            now=_utc_now_naive(),
            employer_id=employer_id,
        )
        job = await JobRepository.get_job_for_employer(
            session=session,
            employer_id=employer_id,
            job_id=job_id,
        )
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        total_applications_received = await JobApplicationRepo.get_total_applications_for_job(
            session=session,
            job_id=job.job_id,
        )
     
        object.__setattr__(job, "total_applications_received", total_applications_received)
        return job



    @staticmethod
    async def list_employer_jobs(
        *,
        session: AsyncSession,
        payload: dict,
        filters: JobListFiltersSchema,
    ) -> JobListResponseSchema:
        user_id_raw = payload.get("user_id")
        if user_id_raw is None:
            raise HTTPException(status_code=403, detail="Access Denied")

        user_id = UUID(user_id_raw)
        await JobService._require_employer(session=session, user_id=user_id)

        profile_q = select(EmployerProfile).where(EmployerProfile.user_id == user_id_raw)
        profile_res = await session.execute(profile_q)
        employer = profile_res.scalar_one_or_none()
        if employer is None:
            raise HTTPException(status_code=403, detail="Employer profile not found")

        await JobRepository.expire_jobs_past_deadline(
            session=session,
            now=_utc_now_naive(),
            employer_id=str(employer.id),
        )

        rows, total = await JobRepository.list_employer_jobs(
            session=session,
            employer_id=str(employer.id),
            filters=filters,
        )

        grid_rows: list[JobListGridRowSchema] = [
            JobListGridRowSchema(
                job_id=job.job_id,
                job_title=job.title,
                job_slug=slugify_job_title(job.title),
                location=job.location,
                employment_type=job.employment_type,
                status=job.status,
                posted_date=posted_display_date(job.created_at),
                application_deadline=job.application_deadline,
                closed_at=job.closed_at,
                closed_reason=job.closed_reason,
                number_of_applications=None,
            )
            for job in rows
        ]



        return JobListResponseSchema(
            rows=grid_rows,
            page=filters.page,
            page_size=filters.page_size,
            total_records=total,
        )

    @staticmethod
    async def update_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
        request: UpdateJobRequestSchema,

        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Job:
        update_data = request.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields provided for update")

        await JobRepository.expire_jobs_past_deadline(
            session=session,
            now=_utc_now_naive(),
            employer_id=employer_id,
        )
        existing_job = await JobRepository.get_job_by_id(
            session=session,
            job_id=job_id,
        )
        if existing_job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if existing_job.employer_id != employer_id:
            raise HTTPException(status_code=403, detail="Access Denied")

        if "application_deadline" in update_data:
            deadline_utc = _normalize_deadline_to_utc_naive(
                update_data.get("application_deadline")
            )
            if deadline_utc is not None:
                is_past_deadline = deadline_utc < _utc_now_naive()
                if is_past_deadline and existing_job.status != "EXPIRED":
                    raise HTTPException(
                        status_code=400,
                        detail="Application deadline cannot be in the past",
                    )
                if (
                    not is_past_deadline
                    and existing_job.status == "EXPIRED"
                    and "status" not in update_data
                ):
                    update_data["status"] = "PUBLISHED"
            update_data["application_deadline"] = deadline_utc

        location_fields = {"country_id", "location_id", "custom_city", "location"}
        if not location_fields.isdisjoint(update_data):
            resolved_location, country_id, location_id, custom_city = await _resolve_job_location(
                session=session,
                country_id=update_data.get("country_id"),
                location_id=update_data.get("location_id"),
                custom_city=update_data.get("custom_city"),
                fallback_location=update_data.get("location"),
            )
            if resolved_location is not None:
                update_data["location"] = resolved_location
            if "country_id" in update_data:
                update_data["country_id"] = country_id
                update_data["location_id"] = location_id
                update_data["custom_city"] = custom_city

        if "skills" in update_data:
            skills = update_data.get("skills")
            if skills is None or not isinstance(skills, list):
                raise HTTPException(status_code=400, detail="Skills are required")

            skills_normalized = _normalize_skills(skills)
            if not (1 <= len(skills_normalized) <= 20):
                raise HTTPException(
                    status_code=400,
                    detail="Skills must contain between 1 and 20 items",
                )
            update_data["skills"] = skills_normalized

        if "job_description" in update_data:
            update_data["job_description"] = _sanitize_job_description(
                update_data.get("job_description")
            )

        if (
            actor_user_id
            and "status" in update_data
            and update_data["status"] in JobRepository.OPEN_STATUSES
            and existing_job.status not in JobRepository.OPEN_STATUSES
        ):
            await JobService._ensure_published_job_limit_available(
                session=session,
                user_id=UUID(str(actor_user_id)),
                employer_id=employer_id,
            )

        # Let the schema/field validators handle the rest of the field-level validation.
        try:
            job = await JobRepository.update_job(
                session=session,
                employer_id=employer_id,
                job_id=job_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                update_data=update_data,
            )
            if job is None:
                raise HTTPException(status_code=403, detail="Access Denied")
            if (
                existing_job.status not in JobRepository.OPEN_STATUSES
                and job.status in JobRepository.OPEN_STATUSES
            ):
                await JobService._notify_matching_job_alerts_for_published_job(
                    session=session,
                    job=job,
                )
            job_name = _job_audit_name(job)
            await ActivityLogService.create_log_for_user_id(
                session=session,
                user_id=actor_user_id,
                actor_role="EMPLOYER",
                action="JOB_UPDATED",
                entity_type="Job",
                entity_id=job.job_id,
                target_entity_name=job_name,
                description=f"Updated job {job_name}",
            )
            return job
        except HTTPException:
            raise


    @staticmethod
    async def reopen_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Job:
        job = await JobRepository.get_job_by_id(session=session, job_id=job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        if job.employer_id != employer_id:
            raise HTTPException(status_code=403, detail="Employer does not own this job")

        if job.status != "CLOSED":
            raise HTTPException(status_code=400, detail="Only closed jobs can be reopened.")

        if actor_user_id:
            await JobService._ensure_published_job_limit_available(
                session=session,
                user_id=UUID(str(actor_user_id)),
                employer_id=employer_id,
            )

        reopened_job = await JobRepository.reopen_job(
            session=session,
            job_id=job_id,
            employer_id=employer_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )

        if reopened_job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        job_name = _job_audit_name(reopened_job)
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=actor_user_id,
            actor_role="EMPLOYER",
            action="JOB_PUBLISHED",
            entity_type="Job",
            entity_id=reopened_job.job_id,
            target_entity_name=job_name,
            description=f"Reopened job {job_name}",
        )
        return reopened_job

    @staticmethod
    async def close_job(

        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
        request: CloseJobRequest,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> Job:
        job = await JobRepository.get_job_by_id(session=session, job_id=job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        if job.employer_id != employer_id:
            raise HTTPException(status_code=403, detail="Employer does not own this job")

        if job.status == "CLOSED":
            raise HTTPException(status_code=409, detail="Job is already closed")

        if job.status not in JobRepository.OPEN_STATUSES:
            raise HTTPException(status_code=400, detail="Only active jobs can be closed")

        closed_job = await JobRepository.close_job(
            session=session,
            job_id=job_id,
            employer_id=employer_id,
            reason=request.reason,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        if closed_job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        job_name = _job_audit_name(closed_job)
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=actor_user_id,
            actor_role="EMPLOYER",
            action="JOB_CLOSED",
            entity_type="Job",
            entity_id=closed_job.job_id,
            target_entity_name=job_name,
            description=f"Closed job {job_name}",
            metadata={"reason": request.reason},
        )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="JOB_CLOSED",
            title="Job closed",
            message=f"Job {job_name} was closed.",
            entity_type="job",
            entity_id=closed_job.job_id,
            target_route=f"/super-admin/jobs/{closed_job.job_id}",
            metadata={"reason": request.reason},
            event_key=f"job_closed:{closed_job.job_id}:{closed_job.closed_at}",
            commit=True,
        )
        return closed_job

    @staticmethod
    async def delete_job(
        *,
        session: AsyncSession,
        employer_id: str,
        job_id: str,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
    ) -> dict:
        try:
            await JobRepository.delete_job(
                job_id=job_id,
                employer_id=employer_id,
                db=session,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                commit=False,
            )
            await ActivityLogService.create_log_for_user_id(
                session=session,
                user_id=actor_user_id,
                actor_role="EMPLOYER",
                action="JOB_DELETED",
                entity_type="Job",
                entity_id=job_id,
                description=f"Deleted job {job_id}",
                commit=False,
            )
            commit = getattr(session, "commit", None)
            if commit:
                await commit()
        except HTTPException:
            raise
        except IntegrityError:
            await session.rollback()
            logger.exception(
                "Failed to delete job due to database integrity constraints.",
                extra={"job_id": job_id, "employer_id": employer_id},
            )
            raise HTTPException(
                status_code=409,
                detail="Job could not be deleted because related records are still being processed.",
            )

        return {
            "success": True,
            "message": "Job deleted successfully.",
        }

    @staticmethod
    async def create_post_job(
        *,
        session: AsyncSession,
        payload: dict,
        employer_id: str,
        request: PostJobRequestSchema,
        idempotency_key: Optional[str],
        request_id: Optional[str] = None,
    ) -> Job:
        user_id_raw = payload.get("user_id")
        user_id = UUID(user_id_raw) if user_id_raw else None
        if user_id is not None:
            await JobService._require_employer(session=session, user_id=user_id)
            if request.status in JobRepository.OPEN_STATUSES:
                await JobService._ensure_published_job_limit_available(
                    session=session,
                    user_id=user_id,
                    employer_id=employer_id,
                )

        _validate_deadline(request.application_deadline)
        application_deadline = _normalize_deadline_to_utc_naive(request.application_deadline)

        resolved_location, country_id, location_id, custom_city = await _resolve_job_location(
            session=session,
            country_id=request.country_id,
            location_id=request.location_id,
            custom_city=request.custom_city,
            fallback_location=request.location,
        )
        display_location = resolved_location or request.location
        if not display_location:
            raise HTTPException(status_code=400, detail="Location is required")

        if request.skills is None or not isinstance(request.skills, list):
            raise HTTPException(status_code=400, detail="Skills are required")

        skills_normalized = _normalize_skills(request.skills)
        if not (1 <= len(skills_normalized) <= 20):
            raise HTTPException(status_code=400, detail="Skills must contain between 1 and 20 items")

        actor_user_id = str(payload.get("user_id")) if payload.get("user_id") else None
        actor_email = payload.get("email")

        if idempotency_key:
            existing_idempotent_job = await JobRepository.get_job_by_idempotency_key(
                session=session,
                employer_id=employer_id,
                idempotency_key=idempotency_key,
            )
            if existing_idempotent_job is not None:
                return existing_idempotent_job

        existing_duplicate = await JobRepository.find_duplicate_active_job(
            session=session,
            employer_id=employer_id,
            job_title=request.job_title,
            company_name=request.company_name,
            location=display_location,
            employment_type=request.employment_type,
            posted_date=_utc_today(),
        )
        if existing_duplicate is not None:
            await JobService._log_duplicate_attempt(
                session=session,
                employer_id=employer_id,
                existing_job=existing_duplicate,
                request=request,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                request_id=request_id,
            )
            raise HTTPException(status_code=409, detail=DUPLICATE_JOB_MESSAGE)

        try:
            job = await JobRepository.create_job(
                session=session,
                employer_id=employer_id,
                job_title=request.job_title,
                job_description=_sanitize_job_description(request.job_description),
                employment_type=request.employment_type,
                experience_required=request.experience_required,
                location=display_location,
                country_id=country_id,
                location_id=location_id,
                custom_city=custom_city,
                work_mode=request.work_mode,
                salary_range=request.salary_range,
                salary_currency=request.salary_currency,
                salary_period=request.salary_period,
                number_of_openings=request.number_of_openings,
                application_deadline=application_deadline,
                company_name=request.company_name,
                contact_email=request.contact_email,
                job_category=request.job_category,
                seniority_level=request.seniority_level,
                team=request.team,
                team_size=request.team_size,
                education=request.education,
                responsibilities=request.responsibilities,
                requirements=request.requirements,
                benefits=request.benefits,
                application_instructions=request.application_instructions,
                working_hours=request.working_hours,
                office_location=request.office_location,
                map_url=request.map_url,
                status=request.status,
                skills=skills_normalized,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )

            await JobService._notify_matching_job_alerts_for_published_job(
                session=session,
                job=job,
            )

            job_name = _job_audit_name(job)
            await ActivityLogService.create_log_for_user_id(
                session=session,
                user_id=actor_user_id,
                actor_role="EMPLOYER",
                action=(
                    "JOB_PUBLISHED"
                    if str(job.status).upper() in {"ACTIVE", "PUBLISHED"}
                    else "JOB_POSTED"
                ),
                entity_type="Job",
                entity_id=job.job_id,
                target_entity_name=job_name,
                description=f"Posted job {job_name}",
                metadata={"status": job.status},
            )
            await NotificationService.create_for_super_admins(
                session,
                notification_type="JOB_POSTED",
                title="Job posted",
                message=f"Job {job_name} was posted.",
                entity_type="job",
                entity_id=job.job_id,
                target_route=f"/super-admin/jobs/{job.job_id}",
                metadata={"status": job.status},
                event_key=f"job_posted:{job.job_id}",
                commit=True,
            )
            return job
        except DuplicateJobIdempotencyKeyError:
            existing = None
            if idempotency_key:
                existing = await JobRepository.get_job_by_idempotency_key(
                    session=session,
                    employer_id=employer_id,
                    idempotency_key=idempotency_key,
                )
            if existing is not None:
                return existing
            await JobService._log_duplicate_attempt(
                session=session,
                employer_id=employer_id,
                existing_job=None,
                request=request,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                request_id=request_id,
            )
            raise HTTPException(status_code=409, detail="Duplicate job not allowed")
        except DuplicateJobPostingError:
            await JobService._log_duplicate_attempt(
                session=session,
                employer_id=employer_id,
                existing_job=None,
                request=request,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                request_id=request_id,
            )
            raise HTTPException(status_code=409, detail=DUPLICATE_JOB_MESSAGE)

    @staticmethod
    async def _log_duplicate_attempt(
        *,
        session: AsyncSession,
        employer_id: str,
        existing_job: Optional[Job],
        request: PostJobRequestSchema,
        actor_user_id: Optional[str],
        actor_email: Optional[str],
        request_id: Optional[str],
    ) -> None:
        await JobRepository.log_duplicate_job_attempt(
            session=session,
            employer_id=employer_id,
            job_id=existing_job.job_id if existing_job else None,
            title=request.job_title,
            company_name=request.company_name,
            location=request.location,
            employment_type=request.employment_type,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            request_id=request_id,
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=actor_user_id,
            actor_role="EMPLOYER",
            action="DUPLICATE_JOB_ATTEMPT",
            entity_type="Job",
            entity_id=existing_job.job_id if existing_job else None,
            target_entity_name=request.job_title,
            description=f"Duplicate job attempt for {request.job_title}",
            metadata={"request_id": request_id} if request_id else None,
        )


async def delete_job_service(
    job_id: str,
    current_user: dict,
    db: AsyncSession,
    employer_id: Optional[str] = None,
) -> dict:
    if employer_id is None:
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == current_user.get("user_id")
            )
        )
        employer = result.scalar_one_or_none()
        if employer is None:
            raise HTTPException(status_code=403, detail="Employer profile not found")
        employer_id = str(employer.id)

    return await JobService.delete_job(
        session=db,
        employer_id=employer_id,
        job_id=job_id,
        actor_user_id=str(current_user.get("user_id")) if current_user.get("user_id") else None,
        actor_email=current_user.get("email"),
    )


