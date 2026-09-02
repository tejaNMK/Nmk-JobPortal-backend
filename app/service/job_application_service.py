from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException

from app.constants.notification_constants import (
    NotificationMessage,
    NotificationTitle,
    NotificationType,
    ReferenceType,
)
from app.job_application_schema import (
    ApplicationNoteCreateSchema,
    ApplicationNoteResponse,
    ApplicationNoteUpdateSchema,
    InterviewLoopDateSchema,
    JobApplicationCardResponse,
    JobApplicationCreateSchema,
    JobApplicationDetailResponse,
    JobApplicationFilterParams,
    JobApplicationListResponse,
    JobApplicationStatusUpdateSchema,
    JobSummary,
    NextStepItemResponse,
    NextStepsResponse,
    NextStepUpsertSchema,
)
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.job import Job
from app.repository.employer_repository.job_repo import JobRepository
from app.repository.job_application_repo import JobApplicationRepo
from app.service.candidate_service import CandidateProfileService
from app.service.notification_service import NotificationService
from app.service.super_admin.activity_log_service import ActivityLogService
from sqlalchemy.ext.asyncio import AsyncSession


class JobApplicationService:
    # A nudge is only meaningful while the candidate is still waiting to
    # hear back — once there's an interview loop, offer, or the
    # application is closed out, "nudge" is replaced by other actions
    # in the UI (view thread / open offer / view notes).
    NUDGEABLE_STATUSES = {"APPLIED", "REVIEW"}
    NUDGE_COOLDOWN = timedelta(hours=72)

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _format_applied_ago(applied_at: datetime | None, now: datetime) -> str:
        """
        Human-readable "applied N days ago" fragment for the nudge
        notification, so the recruiter has application context (when
        the candidate applied) without having to open the record.
        """
        if applied_at is None:
            return "recently"
        days = (now - applied_at).days
        if days <= 0:
            return "today"
        if days == 1:
            return "1 day ago"
        return f"{days} days ago"

    @staticmethod
    def _ensure_job_accepting_applications(job: Job) -> None:
        now = JobApplicationService._utc_now_naive()
        deadline = getattr(job, "application_deadline", None)
        if deadline is not None and deadline.tzinfo is not None:
            deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)

        if (
            job.status not in JobApplicationRepo.OPEN_JOB_STATUSES
            or job.closed_at is not None
            or (deadline is not None and deadline < now)
        ):
            raise HTTPException(
                status_code=409,
                detail="This job is no longer accepting applications.",
            )

    @staticmethod
    async def _notify_employer_application_event(
        *,
        session: AsyncSession,
        job: Job,
        application_id: str,
        candidate_id: str,
        event: str,
    ) -> None:
        if not hasattr(session, "execute"):
            return

        employer_user_id = await JobApplicationRepo.get_employer_user_id_for_job(
            session,
            job,
        )
        if not employer_user_id:
            return

        candidate_name = await JobApplicationRepo.get_candidate_display_name(
            session,
            candidate_id,
        )
        job_title = getattr(job, "title", None) or "your job"

        if event == "withdrawn":
            title = NotificationTitle.APPLICATION_WITHDRAWN
            message = NotificationMessage.APPLICATION_WITHDRAWN.format(
                candidate_name=candidate_name,
                job_title=job_title,
            )
            notification_type = NotificationType.APPLICATION_WITHDRAWN
            event_key = f"application:withdrawn:{application_id}"
        else:
            title = NotificationTitle.APPLICATION_RECEIVED
            message = NotificationMessage.APPLICATION_RECEIVED.format(
                candidate_name=candidate_name,
                job_title=job_title,
            )
            notification_type = NotificationType.APPLICATION_RECEIVED
            event_key = f"application:received:{application_id}"

        await NotificationService.create_notification(
            session=session,
            recipient_id=employer_user_id,
            recipient_role="ROLE_EMPLOYER",
            title=title,
            message=message,
            notification_type=notification_type,
            reference_type=ReferenceType.APPLICATION,
            reference_id=application_id,
            entity_type=ReferenceType.JOB,
            entity_id=getattr(job, "job_id", None),
            target_route=f"/employer/applications/{application_id}",
            metadata={
                "job_id": getattr(job, "job_id", None),
                "job_title": job_title,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
            },
            event_key=event_key,
        )

    @staticmethod
    def _resume_snapshot(resume) -> dict:
        if not resume:
            return {}
        return {
            "resume_file_name_snapshot": getattr(resume, "file_name", None),
            "resume_blob_ref_snapshot": getattr(resume, "blob_ref", None),
            "resume_file_path_snapshot": getattr(resume, "file_path", None),
            "resume_file_size_snapshot": getattr(resume, "file_size", None),
        }

    @staticmethod
    async def apply_for_job(session: AsyncSession, user_id: UUID, data: JobApplicationCreateSchema) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        if not candidate_id:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        await JobRepository.expire_jobs_past_deadline(
            session=session,
            now=JobApplicationService._utc_now_naive(),
        )
        job = await JobApplicationRepo.get_job_for_application(session, data.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job is no longer available.")
        JobApplicationService._ensure_job_accepting_applications(job)

        selected_resume = None
        if data.resume_id:
            selected_resume = await JobApplicationRepo.get_resume_for_candidate(
                session=session,
                candidate_id=candidate_id,
                resume_id=data.resume_id,
            )
            if not selected_resume:
                raise HTTPException(status_code=404, detail="Resume not found")

        if await JobApplicationRepo.application_exists(session, candidate_id, data.job_id):
            raise HTTPException(status_code=409, detail="You have already applied for this job")

        application = JobApplication(
            candidate_id=candidate_id,
            job_id=data.job_id,
            resume_id=data.resume_id,
            **JobApplicationService._resume_snapshot(selected_resume),
            cover_letter_text=data.cover_letter_text,
            source=data.source,
            referral_contact=data.referral_contact,
            application_status="APPLIED",
            created_by=str(user_id),
        )
        try:
            created = await JobApplicationRepo.create_application(
                session,
                application,
                commit=False,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        await JobApplicationService._notify_employer_application_event(
            session=session,
            job=job,
            application_id=created.application_id,
            candidate_id=candidate_id,
            event="received",
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            actor_role="CANDIDATE",
            action="JOB_APPLIED",
            entity_type="JobApplication",
            entity_id=created.application_id,
            target_entity_name=job.title,
            description=f"Applied for job {job.title}",
            metadata={"job_id": data.job_id, "candidate_id": candidate_id},
        )
        return {
            "message": "Application submitted successfully",
            "application_id": created.application_id,
            "application_status": created.application_status,
        }

    @staticmethod
    async def apply_for_job_with_resume_upload(
        session: AsyncSession,
        user_id: UUID,
        data: JobApplicationCreateSchema,
        filename: str | None,
        content_type: str | None,
        contents: bytes,
    ) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        if not candidate_id:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        await JobRepository.expire_jobs_past_deadline(
            session=session,
            now=JobApplicationService._utc_now_naive(),
        )
        job = await JobApplicationRepo.get_job_for_application(session, data.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job is no longer available.")
        JobApplicationService._ensure_job_accepting_applications(job)

        if await JobApplicationRepo.application_exists(session, candidate_id, data.job_id):
            raise HTTPException(status_code=409, detail="You have already applied for this job")

        uploaded_resume = await CandidateProfileService.upload_resume_file(
            session=session,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            contents=contents,
            check_duplicate=False,
        )

        application = JobApplication(
            candidate_id=candidate_id,
            job_id=data.job_id,
            resume_id=uploaded_resume.resume_id,
            resume_file_name_snapshot=uploaded_resume.file_name,
            resume_blob_ref_snapshot=uploaded_resume.blob_ref,
            resume_file_path_snapshot=uploaded_resume.file_path,
            resume_file_size_snapshot=uploaded_resume.file_size,
            cover_letter_text=data.cover_letter_text,
            source=data.source,
            referral_contact=data.referral_contact,
            application_status="APPLIED",
            created_by=str(user_id),
        )
        try:
            created = await JobApplicationRepo.create_application(
                session,
                application,
                commit=False,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        await JobApplicationService._notify_employer_application_event(
            session=session,
            job=job,
            application_id=created.application_id,
            candidate_id=candidate_id,
            event="received",
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            actor_role="CANDIDATE",
            action="JOB_APPLIED",
            entity_type="JobApplication",
            entity_id=created.application_id,
            target_entity_name=job.title,
            description=f"Applied for job {job.title}",
            metadata={
                "job_id": data.job_id,
                "candidate_id": candidate_id,
                "resume_id": uploaded_resume.resume_id,
            },
        )
        return {
            "message": "Application submitted successfully",
            "application_id": created.application_id,
            "application_status": created.application_status,
            "resume_id": uploaded_resume.resume_id,
            "resume_file_name": uploaded_resume.file_name,
        }

    @staticmethod
    async def list_applications(session: AsyncSession, user_id: UUID, filters: JobApplicationFilterParams) -> JobApplicationListResponse:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        if not candidate_id:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        total, apps = await JobApplicationRepo.get_applications_for_candidate(
            session=session,
            candidate_id=candidate_id,
            status=filters.status,
            source=filters.source,
            search=filters.search,
            date_from=filters.date_from,
            date_to=filters.date_to,
            sort_by=filters.sort_by,
            page=filters.page,
            page_size=filters.page_size,
        )

        # Batched lookup (single query) so N cards don't cost N queries —
        # gives each card its last-nudge timestamp for button state.
        last_nudge_by_application = await NotificationService.get_latest_notifications_for_references(
            session=session,
            notification_type=NotificationType.APPLICATION_NUDGE,
            reference_type=ReferenceType.APPLICATION,
            reference_ids=[app.application_id for app in apps],
        )

        cards: list[JobApplicationCardResponse] = []
        for app in apps:

            company = await JobApplicationRepo.get_company_for_job(session, app.job)
            company_name = app.job.company_name or (company.company_name if company else None)
            logo = company.logo_path if company else None

            card = JobApplicationCardResponse(
                application_id=app.application_id,
                application_status=app.application_status,
                applied_at=app.applied_at,
                source=app.source,
                referral_contact=app.referral_contact,
                job=JobSummary(
                    job_id=app.job.job_id,
                    title=app.job.title,
                    location=app.job.location,
                    team=app.job.team,
                    work_mode=app.job.work_mode,
                    employment_type=app.job.employment_type,
                    salary_min=app.job.salary_min,
                    salary_max=app.job.salary_max,
                    application_deadline=app.job.application_deadline,
                    status=app.job.status,
                    company_name=company_name,
                    company_logo=logo,
                ),
                interview_loop_date=app.interview_loop_date,
                next_step_text=app.next_step_text,
                has_notes=any(not n.is_deleted for n in (app.notes or [])),
                last_nudge_sent_at=last_nudge_by_application.get(app.application_id),
            )
            cards.append(card)

        return JobApplicationListResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            items=cards,
        )

    @staticmethod
    async def get_application_detail(session: AsyncSession, user_id: UUID, application_id: str) -> JobApplicationDetailResponse:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        if not candidate_id:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        app = await JobApplicationRepo.get_application_by_id(session, application_id, candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        company = await JobApplicationRepo.get_company_for_job(session, app.job)
        company_name = app.job.company_name or (company.company_name if company else None)
        logo = company.logo_path if company else None

        return JobApplicationDetailResponse(
            application_id=app.application_id,
            application_status=app.application_status,
            applied_at=app.applied_at,
            updated_at=app.updated_at,
            source=app.source,
            referral_contact=app.referral_contact,
            cover_letter_text=app.cover_letter_text,
            interview_loop_date=app.interview_loop_date,
            next_step_text=app.next_step_text,
            next_step_due=app.next_step_due,
            job=JobSummary(
                job_id=app.job.job_id,
                title=app.job.title,
                location=app.job.location,
                team=app.job.team,
                work_mode=app.job.work_mode,
                employment_type=app.job.employment_type,
                salary_min=app.job.salary_min,
                salary_max=app.job.salary_max,
                application_deadline=app.job.application_deadline,
                status=app.job.status,
                company_name=company_name,
                company_logo=logo,
            ),
            status_history=[
                {
                    "history_id": h.history_id,
                    "old_status": h.old_status,
                    "new_status": h.new_status,
                    "changed_at": h.changed_at,
                }
                for h in sorted(app.status_history, key=lambda h: h.changed_at)
            ],
            interviews=[
                {
                    "interview_id": i.interview_id,
                    "scheduled_at": i.scheduled_at,
                    "mode": i.mode,
                    "location_or_link": i.location_or_link,
                    "interviewer_name": i.interviewer_name,
                    "status": i.status,
                    "notes": i.notes,
                }
                for i in sorted(app.interviews, key=lambda i: i.scheduled_at)
            ],
            notes=[
                {
                    "note_id": n.note_id,
                    "note_text": n.note_text,
                    "created_by": n.created_by,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at,
                }
                for n in app.notes
                if not n.is_deleted
            ],
        )

    @staticmethod
    async def update_status(session: AsyncSession, user_id: UUID, application_id: str, data: JobApplicationStatusUpdateSchema) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        updated = await JobApplicationRepo.update_status(session=session, application_id=application_id, candidate_id=candidate_id, new_status=data.application_status, changed_by=user_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"message": "Status updated successfully", "application_id": application_id, "application_status": data.application_status}

    @staticmethod
    async def upsert_next_step(session: AsyncSession, user_id: UUID, application_id: str, data: NextStepUpsertSchema) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        updated = await JobApplicationRepo.upsert_next_step(session=session, application_id=application_id, candidate_id=candidate_id, next_step_text=data.next_step_text, next_step_due=data.next_step_due)
        if not updated:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"message": "Next step saved", "application_id": application_id}

    @staticmethod
    async def set_interview_loop_date(session: AsyncSession, user_id: UUID, application_id: str, data: InterviewLoopDateSchema) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        updated = await JobApplicationRepo.set_interview_loop_date(session=session, application_id=application_id, candidate_id=candidate_id, interview_loop_date=data.interview_loop_date)
        if not updated:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"message": "Interview loop date set", "interview_loop_date": str(data.interview_loop_date)}

    @staticmethod
    async def send_nudge(session: AsyncSession, user_id: UUID, application_id: str) -> dict:
        """
        Lets a candidate ping the recruiter on an application that's
        still awaiting review. Creates an in-app notification for the
        recruiter and rate-limits repeat nudges on the same application.
        """
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        if not candidate_id:
            raise HTTPException(status_code=404, detail="Candidate profile not found")

        app = await JobApplicationRepo.get_application_by_id(session, application_id, candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        if app.application_status not in JobApplicationService.NUDGEABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="A nudge can only be sent while your application is awaiting review.",
            )

        recruiter_user_id = await JobApplicationRepo.get_employer_user_id_for_job(session, app.job)
        if not recruiter_user_id:
            raise HTTPException(status_code=404, detail="No recruiter could be found for this job")

        candidate_name = await JobApplicationRepo.get_candidate_display_name(session, candidate_id)

        latest = await NotificationService.get_latest_notification(
            session=session,
            recipient_id=recruiter_user_id,
            notification_type=NotificationType.APPLICATION_NUDGE,
            reference_type=ReferenceType.APPLICATION,
            reference_id=application_id,
        )
        now = JobApplicationService._utc_now_naive()
        if latest is not None:
            elapsed = now - latest.created_at
            if elapsed < JobApplicationService.NUDGE_COOLDOWN:
                remaining = JobApplicationService.NUDGE_COOLDOWN - elapsed
                hours_left = max(1, -(-int(remaining.total_seconds()) // 3600))  # ceil division
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "You already nudged this recruiter recently. "
                        f"You can send another nudge in about {hours_left} hour(s)."
                    ),
                )

        applied_ago = JobApplicationService._format_applied_ago(app.applied_at, now)
        notification = await NotificationService.create_notification(
            session=session,
            recipient_id=recruiter_user_id,
            recipient_role="ROLE_EMPLOYER",
            title=f"{NotificationTitle.APPLICATION_NUDGE}: {candidate_name}",
            message=NotificationMessage.APPLICATION_NUDGE.format(
                candidate_name=candidate_name,
                job_title=app.job.title,
                applied_ago=applied_ago,
            ),
            notification_type=NotificationType.APPLICATION_NUDGE,
            reference_type=ReferenceType.APPLICATION,
            reference_id=application_id,
            entity_type=ReferenceType.APPLICATION,
            entity_id=application_id,
            target_route=f"/employer/applications/{application_id}",
            metadata={
                "application_id": application_id,
                "job_id": app.job_id,
                "job_title": app.job.title,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "applied_ago": applied_ago,
                "action_required": True,
                "priority": "HIGH",
            },
        )
        if notification is None:
            raise HTTPException(
                status_code=502,
                detail="Couldn't notify the recruiter right now. Please try again.",
            )

        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            actor_role="CANDIDATE",
            action="APPLICATION_NUDGE_SENT",
            entity_type="JobApplication",
            entity_id=application_id,
            target_entity_name=app.job.title,
            description=f"Sent a nudge to the recruiter for {app.job.title}",
            metadata={"candidate_id": candidate_id, "recruiter_user_id": recruiter_user_id},
        )

        return {
            "message": "Nudge sent to the recruiter",
            "application_id": application_id,
            "last_nudge_sent_at": notification.created_at,
        }

    @staticmethod
    async def withdraw_application(session: AsyncSession, user_id: UUID, application_id: str) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        app = None
        if hasattr(session, "execute"):
            app = await JobApplicationRepo.get_application_by_id(
                session=session,
                application_id=application_id,
                candidate_id=candidate_id,
            )
        withdrawn = await JobApplicationRepo.withdraw_application(
            session=session,
            application_id=application_id,
            candidate_id=candidate_id,
            changed_by=user_id,
        )
        if not withdrawn:
            raise HTTPException(status_code=404, detail="Application not found or already withdrawn")
        if app and getattr(app, "job", None):
            await JobApplicationService._notify_employer_application_event(
                session=session,
                job=app.job,
                application_id=application_id,
                candidate_id=candidate_id,
                event="withdrawn",
            )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            actor_role="CANDIDATE",
            action="APPLICATION_WITHDRAWN",
            entity_type="JobApplication",
            entity_id=application_id,
            description=f"Withdrew application {application_id}",
            metadata={"candidate_id": candidate_id},
        )
        return {
            "message": "Application withdrawn successfully",
            "application_id": application_id,
            "application_status": "WITHDRAWN",
        }

    @staticmethod
    async def add_note(session: AsyncSession, user_id: UUID, application_id: str, data: ApplicationNoteCreateSchema) -> ApplicationNoteResponse:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        app = await JobApplicationRepo.get_application_by_id(session=session, application_id=application_id, candidate_id=candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        note = await JobApplicationRepo.add_note(session=session, application_id=application_id, note_text=data.note_text, created_by=str(user_id))
        return ApplicationNoteResponse.model_validate(note)

    @staticmethod
    async def get_notes(session: AsyncSession, user_id: UUID, application_id: str) -> list[ApplicationNoteResponse]:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        app = await JobApplicationRepo.get_application_by_id(session=session, application_id=application_id, candidate_id=candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        notes = await JobApplicationRepo.get_notes(session=session, application_id=application_id)
        return [ApplicationNoteResponse.model_validate(n) for n in notes]

    @staticmethod
    async def update_note(session: AsyncSession, user_id: UUID, application_id: str, note_id: str, data: ApplicationNoteUpdateSchema) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        app = await JobApplicationRepo.get_application_by_id(session=session, application_id=application_id, candidate_id=candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        updated = await JobApplicationRepo.update_note(session=session, note_id=note_id, application_id=application_id, note_text=data.note_text)
        if not updated:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"message": "Note updated"}

    @staticmethod
    async def delete_note(session: AsyncSession, user_id: UUID, application_id: str, note_id: str) -> dict:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        app = await JobApplicationRepo.get_application_by_id(session=session, application_id=application_id, candidate_id=candidate_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        deleted = await JobApplicationRepo.delete_note(session=session, note_id=note_id, application_id=application_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"message": "Note deleted"}

    @staticmethod
    async def get_next_steps_panel(session: AsyncSession, user_id: UUID) -> NextStepsResponse:
        candidate_id = await JobApplicationRepo._get_candidate_id(session, user_id)
        apps = await JobApplicationRepo.get_next_steps(session=session, candidate_id=candidate_id)

        items: list[NextStepItemResponse] = []
        for app in apps:
            company = await JobApplicationRepo.get_company_for_job(session=session, job=app.job)
            company_name = app.job.company_name or (company.company_name if company else None)
            items.append(
                NextStepItemResponse(
                    application_id=app.application_id,
                    job_title=app.job.title,
                    company_name=company_name,
                    next_step_text=app.next_step_text,
                    next_step_due=app.next_step_due,
                )
            )
        return NextStepsResponse(items=items)
