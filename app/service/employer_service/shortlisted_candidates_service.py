from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from app.utils.utc import utc_now_naive

ALLOWED_STATUS_TRANSITIONS = {
    "SHORTLISTED": [
        "SHORTLISTED",
        "INTERVIEW_SCHEDULED",
        "ON_HOLD",
        "REJECTED",
    ],
    "INTERVIEW_SCHEDULED": [
        "HIRED",
        "ON_HOLD",
        "REJECTED",
    ],
    "ON_HOLD": [
        "ON_HOLD",
        "SHORTLISTED",
        "INTERVIEW_SCHEDULED",
        "REJECTED",
    ],
    "REJECTED": [
        "REJECTED",
        "SHORTLISTED",
    ],
    "HIRED": [
        "HIRED",
        "SHORTLISTED",
        "REJECTED",
    ],
}

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.notification_constants import (
    NotificationMessage,
    NotificationTitle,
    NotificationType,
    ReferenceType,
)
from app.repository.employer_repository.shortlisted_candidates_repo import (
    ShortlistedCandidatesRepo,
)
from app.model.candidate_model.application_status_history import ApplicationStatusHistory
from app.service.notification_service import NotificationService
from app.service.super_admin.activity_log_service import ActivityLogService
from app.utils.image_urls import resolve_profile_image_url
from app.schema.shortlisted_candidates import (
    ShortlistedCandidateFilterParams,
    ShortlistedCandidateListItem,
    ShortlistedCandidateListResponse,
    ShortlistedCandidateProfileResponse,
    ResumeDownloadResponse,
)


class ShortlistedCandidatesService:
    RECRUITMENT_LOG_ACTIONS = {
        "SHORTLISTED": "CANDIDATE_SHORTLISTED",
        "REJECTED": "CANDIDATE_REJECTED",
        "HIRED": "CANDIDATE_HIRED",
    }

    @staticmethod
    def _application_resume(application, resume):
        if resume:
            return resume
        if not (
            getattr(application, "resume_blob_ref_snapshot", None)
            or getattr(application, "resume_file_path_snapshot", None)
            or getattr(application, "resume_file_name_snapshot", None)
        ):
            return None
        return SimpleNamespace(
            resume_id=getattr(application, "resume_id", None),
            file_name=getattr(application, "resume_file_name_snapshot", None),
            file_path=getattr(application, "resume_file_path_snapshot", None),
            blob_ref=getattr(application, "resume_blob_ref_snapshot", None),
            file_size=getattr(application, "resume_file_size_snapshot", None),
        )

    @staticmethod
    async def _log_recruitment_activity(
        session: AsyncSession,
        user_id: UUID,
        application,
        action: str,
        previous_status: str | None = None,
    ) -> None:
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            actor_role="EMPLOYER",
            action=action,
            entity_type="JobApplication",
            entity_id=application.application_id,
            target_entity_name=application.job_id,
            description=f"{action.replace('_', ' ').title()} for application {application.application_id}",
            metadata={
                "job_id": application.job_id,
                "candidate_id": application.candidate_id,
                "previous_status": previous_status,
                "new_status": application.application_status,
            },
        )

    @staticmethod
    async def _notify_candidate_status_event(
        *,
        session: AsyncSession,
        employer_id: str,
        application_id: str,
        status: str,
    ) -> None:
        row = await ShortlistedCandidatesRepo.get_application_details(
            session=session,
            employer_id=employer_id,
            application_id=application_id,
        )
        if not row:
            return
        application, _profile, user, _resume, job = row
        candidate_user_id = str(getattr(user, "user_id", "") or "")
        if not candidate_user_id:
            return
        candidate_name = (
            f"{getattr(user, 'first_name', '') or ''} "
            f"{getattr(user, 'last_name', '') or ''}"
        ).strip() or "Candidate"
        job_title = getattr(job, "title", None) or "your application"
        normalized_status = status.upper()
        notification_type_by_status = {
            "SHORTLISTED": NotificationType.APPLICATION_SHORTLISTED,
            "REJECTED": NotificationType.APPLICATION_REJECTED,
            "HIRED": NotificationType.APPLICATION_HIRED,
        }
        title_by_status = {
            "SHORTLISTED": NotificationTitle.APPLICATION_SHORTLISTED,
            "REJECTED": NotificationTitle.APPLICATION_REJECTED,
            "HIRED": NotificationTitle.APPLICATION_HIRED,
        }
        message_by_status = {
            "SHORTLISTED": NotificationMessage.APPLICATION_SHORTLISTED,
            "REJECTED": NotificationMessage.APPLICATION_REJECTED,
            "HIRED": NotificationMessage.APPLICATION_HIRED,
        }
        notification_type = notification_type_by_status.get(normalized_status)
        if not notification_type:
            return
        await NotificationService.create_notification(
            session=session,
            recipient_id=candidate_user_id,
            recipient_role="ROLE_CANDIDATE",
            title=title_by_status[normalized_status],
            message=message_by_status[normalized_status].format(
                job_title=job_title,
            ),
            notification_type=notification_type,
            reference_type=ReferenceType.APPLICATION,
            reference_id=application_id,
            entity_type=ReferenceType.APPLICATION,
            entity_id=application_id,
            target_route=f"/candidate/applications/{application_id}",
            metadata={
                "application_id": application_id,
                "job_id": getattr(application, "job_id", None),
                "job_title": job_title,
                "candidate_id": getattr(application, "candidate_id", None),
                "candidate_name": candidate_name,
                "status": normalized_status,
            },
            event_key=f"application:{normalized_status.lower()}:{application_id}",
        )

    @staticmethod
    async def shortlist_candidate(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ):
        employer_id = await ShortlistedCandidatesRepo.get_employer_id(session, user_id)
        if not employer_id:
            raise HTTPException(status_code=403, detail="Recruiter profile not found")

        application = await ShortlistedCandidatesRepo.get_application_for_employer(
            session=session,
            employer_id=employer_id,
            application_id=application_id,
        )

        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        if (application.application_status or "").upper() == "SHORTLISTED" and application.shortlisted_at is not None:
            return {
                "application_id": application.application_id,
                "job_id": application.job_id,
                "status": application.application_status,
                "date_shortlisted": application.shortlisted_at,
            }

        previous_status = application.application_status
        updated = await ShortlistedCandidatesRepo.update_application_shortlist_status(
            session=session,
            application_id=application_id,
            status="SHORTLISTED",
            changed_by=user_id,
            previous_status=previous_status,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Application not found")

        await ShortlistedCandidatesService._log_recruitment_activity(
            session=session,
            user_id=user_id,
            application=updated,
            action="CANDIDATE_SHORTLISTED",
            previous_status=previous_status,
        )
        await ShortlistedCandidatesService._notify_candidate_status_event(
            session=session,
            employer_id=employer_id,
            application_id=updated.application_id,
            status="SHORTLISTED",
        )

        return {
            "application_id": updated.application_id,
            "job_id": updated.job_id,
            "status": updated.application_status,
            "date_shortlisted": updated.shortlisted_at,
        }

    @staticmethod
    async def unshortlist_candidate(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ):
        employer_id = await ShortlistedCandidatesRepo.get_employer_id(session, user_id)
        if not employer_id:
            raise HTTPException(status_code=403, detail="Recruiter profile not found")

        application = await ShortlistedCandidatesRepo.get_application_for_employer(
            session=session,
            employer_id=employer_id,
            application_id=application_id,
        )

        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        # Remove from shortlist: revert to APPLIED
        updated = await ShortlistedCandidatesRepo.update_application_shortlist_status(
            session=session,
            application_id=application_id,
            status="APPLIED",
            clear_shortlisted_at=True,
            changed_by=user_id,
            previous_status=application.application_status,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Application not found")

        return {
            "application_id": updated.application_id,
            "job_id": updated.job_id,
            "status": updated.application_status,
        }

    @staticmethod
    async def list_shortlisted_candidates(
        session: AsyncSession,
        user_id: UUID,
        filters: ShortlistedCandidateFilterParams,
    ) -> ShortlistedCandidateListResponse:

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        return await ShortlistedCandidatesService._list_candidates_by_statuses(
            session=session,
            employer_id=employer_id,
            filters=filters,
            statuses=[
                "SHORTLISTED",
                "INTERVIEW_SCHEDULED",
                "ON_HOLD",
                "HIRED",
            ],
        )

    @staticmethod
    async def list_rejected_candidates(
        session: AsyncSession,
        user_id: UUID,
        filters: ShortlistedCandidateFilterParams,
    ) -> ShortlistedCandidateListResponse:

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        return await ShortlistedCandidatesService._list_candidates_by_statuses(
            session=session,
            employer_id=employer_id,
            filters=filters,
            statuses=["REJECTED"],
        )

    @staticmethod
    async def _list_candidates_by_statuses(
        session: AsyncSession,
        employer_id: str,
        filters: ShortlistedCandidateFilterParams,
        statuses: list[str],
    ) -> ShortlistedCandidateListResponse:

        total, rows = (
            await ShortlistedCandidatesRepo.get_shortlisted_candidates(
                session=session,
                employer_id=employer_id,
                search=filters.search,
                status=filters.status,
                job_role=filters.job_role,
                date_from=filters.date_from,
                date_to=filters.date_to,
                page=filters.page,
                page_size=filters.page_size,
                sort_by=filters.sort_by,
                statuses=statuses,
            )
        )

        items = []

        for app, profile, user, resume, job in rows:
            resume = ShortlistedCandidatesService._application_resume(app, resume)

            full_name = (
                f"{user.first_name} {user.last_name or ''}"
            ).strip()

            items.append(
                ShortlistedCandidateListItem(
                    application_id=app.application_id,
                    job_id=app.job_id,
                    candidate_id=app.candidate_id,
                    candidate_name=full_name,
                    email=user.email,
                    phone_number=user.mobile_number,
                    profile_image_url=resolve_profile_image_url(
                        getattr(user, "profile_image_url", None)
                    ),
                    job_role=job.title,
                    job_title=job.title,
                    resume_name=resume.file_name if resume else None,
                    referral_contact=app.referral_contact,
                    source=app.source,
                    application_date=app.applied_at,
                    applied_at=app.applied_at,
                    updated_at=getattr(app, "updated_at", app.applied_at),
                    status=app.application_status,
                    application_status=app.application_status,
                    rating=app.candidate_rating,
                    date_shortlisted=app.shortlisted_at,
                )
            )

        return ShortlistedCandidateListResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            items=items,
        )

    @staticmethod
    async def get_shortlisted_candidate_profile(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ) -> ShortlistedCandidateProfileResponse:

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        row = await ShortlistedCandidatesRepo.get_application_details(
            session,
            employer_id,
            application_id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found"
            )

        app, profile, user, resume, job = row
        resume = ShortlistedCandidatesService._application_resume(app, resume)

        return ShortlistedCandidateProfileResponse(
            application_id=app.application_id,
            job_id=app.job_id,
            candidate_id=app.candidate_id,
            candidate_name=f"{user.first_name} {user.last_name or ''}".strip(),
            email=user.email,
            phone_number=user.mobile_number,
            profile_image_url=resolve_profile_image_url(
                getattr(user, "profile_image_url", None)
            ),
            headline=profile.headline,
            summary=profile.summary,
            total_experience=float(profile.total_experience)
            if profile.total_experience
            else None,
            current_location=profile.current_location,
            preferred_location=profile.preferred_location,
            skills_summary=profile.skills_summary,
            job_role=job.title,
            referral_contact=app.referral_contact,
            source=app.source,
            status=app.application_status,
            application_date=app.applied_at,
            date_shortlisted=app.shortlisted_at,
            rating=app.candidate_rating,
            resume_name=resume.file_name if resume else None,
            resume_path=resume.file_path if resume else None,
        )

    @staticmethod
    async def get_resume(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ) -> ResumeDownloadResponse:

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        row = await ShortlistedCandidatesRepo.get_application_details(
            session,
            employer_id,
            application_id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Resume not found"
            )

        app, profile, user, resume, job = row
        resume = ShortlistedCandidatesService._application_resume(app, resume)

        if not resume:
            raise HTTPException(
                status_code=404,
                detail="Resume not found"
            )

        return ResumeDownloadResponse(
            resume_id=resume.resume_id,
            file_name=resume.file_name,
            file_path=resume.file_path,
        )

    @staticmethod
    async def update_rating(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
        rating: int,
    ):

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        application = await ShortlistedCandidatesRepo.update_rating(
            session=session,
            application_id=application_id,
            rating=rating,
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found"
            )

        return {
            "application_id": application.application_id,
            "rating": application.candidate_rating,
        }
    
    @staticmethod
    async def update_status(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
        status: str,
        reason: str | None = None,
    ):

        employer_id = await ShortlistedCandidatesRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        application = (
            await ShortlistedCandidatesRepo.get_application_for_employer(
                session=session,
                employer_id=employer_id,
                application_id=application_id,
            )
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found"
            )

        current_status = (
            application.application_status or ""
        ).upper()

        new_status = status.upper()

        allowed_statuses = (
            ALLOWED_STATUS_TRANSITIONS.get(
                current_status,
                []
            )
        )

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status transition "
                    f"from {current_status} "
                    f"to {new_status}"
                )
            )

        if new_status == current_status:
            return {
                "application_id": application.application_id,
                "job_id": application.job_id,
                "candidate_id": application.candidate_id,
                "previous_status": current_status,
                "application_status": application.application_status,
                "updated_at": application.updated_at,
                "status": application.application_status,
            }

        application = await ShortlistedCandidatesRepo.update_status(
            session=session,
            application_id=application_id,
            status=new_status,
            changed_by=user_id,
            previous_status=current_status,
            reason=reason,
        )

        log_action = ShortlistedCandidatesService.RECRUITMENT_LOG_ACTIONS.get(new_status)
        if log_action:
            await ShortlistedCandidatesService._log_recruitment_activity(
                session=session,
                user_id=user_id,
                application=application,
                action=log_action,
                previous_status=current_status,
            )
            await ShortlistedCandidatesService._notify_candidate_status_event(
                session=session,
                employer_id=employer_id,
                application_id=application.application_id,
                status=new_status,
            )

        return {
            "application_id": application.application_id,
            "job_id": application.job_id,
            "candidate_id": application.candidate_id,
            "previous_status": current_status,
            "application_status": application.application_status,
            "updated_at": application.updated_at,
            "status": application.application_status,
        }
    
    @staticmethod
    async def bulk_update_status(
        session: AsyncSession,
        user_id: UUID,
        application_ids: list[str],
        status: str,
    ):

        employer_id = (
            await ShortlistedCandidatesRepo.get_employer_id(
                session,
                user_id
            )
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        applications = (
            await ShortlistedCandidatesRepo.get_applications_by_ids(
                session,
                application_ids,
                employer_id=employer_id,
            )
        )

        updated = []

        for application in applications:

            current_status = (
                application.application_status or ""
            ).upper()

            new_status = status.upper()

            allowed_statuses = (
                ALLOWED_STATUS_TRANSITIONS.get(
                    current_status,
                    []
                )
            )

            if new_status not in allowed_statuses:
                continue

            if new_status == current_status:
                updated.append(application.application_id)
                continue

            application.application_status = new_status
            application.updated_at = utc_now_naive()
            if new_status == "SHORTLISTED" and not application.shortlisted_at:
                application.shortlisted_at = application.updated_at
            session.add(
                ApplicationStatusHistory(
                    application_id=application.application_id,
                    old_status=current_status,
                    new_status=new_status,
                    changed_by=user_id,
                )
            )

            updated.append(
                application.application_id
            )

        await session.commit()

        log_action = ShortlistedCandidatesService.RECRUITMENT_LOG_ACTIONS.get(
            status.upper()
        )
        if log_action:
            for application in applications:
                if application.application_id in updated:
                    await ShortlistedCandidatesService._log_recruitment_activity(
                        session=session,
                        user_id=user_id,
                        application=application,
                        action=log_action,
                    )
                    await ShortlistedCandidatesService._notify_candidate_status_event(
                        session=session,
                        employer_id=employer_id,
                        application_id=application.application_id,
                        status=status.upper(),
                    )

        return {
            "updated_count": len(updated),
            "application_ids": updated,
            "status": status.upper(),
        }
    
    @staticmethod
    async def bulk_reject(
        session: AsyncSession,
        user_id: UUID,
        application_ids: list[str],
        reason: str | None = None,
    ):

        return await (
            ShortlistedCandidatesService.bulk_update_status(
                session=session,
                user_id=user_id,
                application_ids=application_ids,
                status="REJECTED",
            )
        )
    
    @staticmethod
    async def get_notes(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ):

        employer_id = await (
            ShortlistedCandidatesRepo.get_employer_id(
                session,
                user_id,
            )
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found",
            )

        application = await (
            ShortlistedCandidatesRepo.get_notes(
                session=session,
                application_id=application_id,
            )
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        return {
            "application_id": application_id,
            "remarks": application.recruiter_notes,
        }
    
    @staticmethod
    async def update_notes(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
        remarks: str,
    ):

        employer_id = await (
            ShortlistedCandidatesRepo.get_employer_id(
                session,
                user_id,
            )
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found",
            )

        application = await (
            ShortlistedCandidatesRepo.update_notes(
                session=session,
                application_id=application_id,
                remarks=remarks,
            )
        )

        if not application:
            raise HTTPException(
                status_code=404,
                detail="Application not found",
            )

        return {
            "application_id": application_id,
            "remarks": application.recruiter_notes,
        }
