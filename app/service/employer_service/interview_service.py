import logging
import mimetypes
import os
from datetime import datetime, timezone
from uuid import UUID
from app.utils.utc import utc_now_naive

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.notification_constants import (
    NotificationTitle,
    NotificationType,
    ReferenceType,
)
from app.model.employer_model.interview_history import InterviewHistory
from app.model.employer_model.interview import Interview
from app.model.employer_model.interviewer import Interviewer
from app.repository.employer_repository.interview_history_repo import (
    InterviewHistoryRepo,
)
from app.repository.employer_repository.interview_interviewer_repo import (
    InterviewInterviewerRepo,
)
from app.repository.employer_repository.interview_repo import InterviewRepo
from app.repository.employer_repository.interviewer_repo import InterviewerRepo
from app.repository.employer_repository.shortlisted_candidates_repo import (
    ShortlistedCandidatesRepo,
)
from app.schema.interview import (
    AssignedInterviewerResponse,
    InterviewRoundsResponse,
    InterviewResponse,
    InterviewerCreateRequest,
    InterviewerLookupItem,
    InterviewerLookupResponse,
    InterviewerListResponse,
    InterviewerResponse,
    InterviewerUpdateRequest,
)
from app.service.authentication.email_service import EmailService
from app.service.notification_service import NotificationService
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service import s3_service


logger = logging.getLogger(__name__)


class InterviewerService:
    ASSIGNED_INTERVIEWER_DELETE_MESSAGE = (
        "This interviewer is assigned to one or more interviews. Remove the "
        "interviewer from those interviews before deleting."
    )

    @staticmethod
    def _response(interviewer: Interviewer) -> InterviewerResponse:
        return InterviewerResponse(
            id=interviewer.id,
            name=interviewer.name,
            email=interviewer.email,
            created_at=(
                interviewer.created_at.isoformat()
                if interviewer.created_at
                else None
            ),
            updated_at=(
                interviewer.updated_at.isoformat()
                if interviewer.updated_at
                else None
            ),
        )

    @staticmethod
    async def create_interviewer(
        session: AsyncSession,
        request: InterviewerCreateRequest,
        performed_by: str | UUID | None = None,
    ) -> InterviewerResponse:
        existing = await InterviewerRepo.get_by_email(
            session=session,
            email=request.email,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Interviewer with this email already exists.",
            )

        interviewer = Interviewer(name=request.name, email=request.email)
        try:
            interviewer = await InterviewerRepo.create(
                session=session,
                interviewer=interviewer,
            )
            await session.commit()
            await session.refresh(interviewer)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Interviewer with this email already exists.",
            ) from exc

        return InterviewerService._response(interviewer)

    @staticmethod
    async def get_interviewer(
        session: AsyncSession,
        interviewer_id: str,
    ) -> InterviewerResponse:
        interviewer = await InterviewerRepo.get_by_id(
            session=session,
            interviewer_id=interviewer_id,
        )
        if not interviewer:
            raise HTTPException(status_code=404, detail="Interviewer not found.")
        return InterviewerService._response(interviewer)

    @staticmethod
    async def list_interviewers(
        session: AsyncSession,
        search: str | None,
        page: int,
        page_size: int,
    ) -> InterviewerListResponse:
        total, interviewers = await InterviewerRepo.list(
            session=session,
            search=search,
            page=page,
            page_size=page_size,
        )
        return InterviewerListResponse(
            items=[
                InterviewerService._response(interviewer)
                for interviewer in interviewers
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def update_interviewer(
        session: AsyncSession,
        interviewer_id: str,
        request: InterviewerUpdateRequest,
        performed_by: str | UUID | None = None,
    ) -> InterviewerResponse:
        interviewer = await InterviewerRepo.get_by_id(
            session=session,
            interviewer_id=interviewer_id,
        )
        if not interviewer:
            raise HTTPException(status_code=404, detail="Interviewer not found.")

        if request.email is not None and request.email != interviewer.email:
            duplicate = await InterviewerRepo.get_by_email(
                session=session,
                email=request.email,
            )
            if duplicate and duplicate.id != interviewer.id:
                raise HTTPException(
                    status_code=409,
                    detail="Interviewer with this email already exists.",
                )
            interviewer.email = request.email

        if request.name is not None:
            interviewer.name = request.name

        interviewer.updated_at = utc_now_naive()
        try:
            session.add(interviewer)
            await session.commit()
            await session.refresh(interviewer)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Interviewer with this email already exists.",
            ) from exc

        return InterviewerService._response(interviewer)

    @staticmethod
    async def delete_interviewer(
        session: AsyncSession,
        interviewer_id: str,
        performed_by: str | UUID | None = None,
    ) -> None:
        interviewer = await InterviewerRepo.get_by_id(
            session=session,
            interviewer_id=interviewer_id,
        )
        if not interviewer:
            raise HTTPException(status_code=404, detail="Interviewer not found.")

        assignment_count = await InterviewerRepo.count_interview_assignments(
            session=session,
            interviewer_id=interviewer_id,
        )
        if assignment_count:
            raise HTTPException(
                status_code=409,
                detail=InterviewerService.ASSIGNED_INTERVIEWER_DELETE_MESSAGE,
            )

        try:
            await InterviewerRepo.delete(session=session, interviewer=interviewer)
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            logger.exception(
                "Failed to delete interviewer because it is still referenced.",
                extra={"interviewer_id": interviewer_id},
            )
            raise HTTPException(
                status_code=409,
                detail=InterviewerService.ASSIGNED_INTERVIEWER_DELETE_MESSAGE,
            ) from exc


class InterviewService:
    INVALID_INTERVIEWER_EMAILS_MESSAGE = (
        "One or more interviewer emails are invalid, inactive, or not eligible."
    )
    MAX_INTERVIEW_ROUNDS = 20
    RESUME_STATUS_ATTACHED = "attached"
    RESUME_STATUS_NOT_PROVIDED = "not_provided"
    RESUME_STATUS_UNAVAILABLE = "unavailable"

    @staticmethod
    async def schedule_interview(
        session: AsyncSession,
        employer_id: str,
        application_id: str,
        request,
        performed_by: str | None = None,
    ):
        application = (
            await ShortlistedCandidatesRepo.get_application_for_employer(
                session=session,
                employer_id=employer_id,
                application_id=application_id,
            )
        )

        if not application:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to schedule interviews for this application.",
            )

        if application.application_status not in [
            "SHORTLISTED",
            "INTERVIEW_SCHEDULED",
        ]:
            raise HTTPException(
                status_code=400,
                detail="Interview can only be scheduled for shortlisted candidates.",
            )

        await InterviewService._validate_round_limit(
            session=session,
            application_id=application_id,
        )

        duplicate = await InterviewRepo.get_duplicate_interview(
            session=session,
            application_id=application_id,
            interview_date=request.interview_date,
            interview_time=request.interview_time,
            round_number=getattr(request, "round_number", None),
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="An interview already exists for the selected date and time.",
            )

        interview = Interview(
            application_id=application_id,
            interview_title=request.interview_title,
            round_number=request.round_number,
            interview_round=InterviewService._schema_value(request.interview_round),
            interview_date=request.interview_date,
            interview_time=request.start_time or request.interview_time,
            end_time=request.end_time,
            timezone=request.timezone,
            mode=InterviewService._schema_value(request.mode),
            meeting_link=(
                str(request.meeting_link)
                if request.meeting_link
                else None
            ),
            interview_location=request.interview_location,
            interviewer_name=request.interviewer_name,
            remarks=request.remarks,
            status="SCHEDULED",
        )

        try:
            interviewer_ids = await InterviewService._resolve_interviewers(
                session=session,
                interviewer_ids=getattr(request, "interviewer_ids", None),
                interviewer_emails=getattr(request, "interviewer_emails", None),
                interviewers=getattr(request, "interviewers", None),
            )

            interview = await InterviewService._create_interview_record(
                session=session,
                interview=interview,
            )

            await InterviewService._update_application_status(
                session=session,
                application_id=application_id,
                status="INTERVIEW_SCHEDULED",
            )

            await InterviewService._replace_interviewers(
                session=session,
                interview=interview,
                interviewer_ids=interviewer_ids,
            )

            await InterviewService._record_history(
                session=session,
                interview=interview,
                employer_id=employer_id,
                performed_by=performed_by,
                action="SCHEDULED",
                previous_values=None,
                new_values=InterviewService._interview_snapshot(interview),
            )
            await ActivityLogService.create_log_for_user_id(
                session=session,
                user_id=performed_by,
                actor_role="EMPLOYER",
                action="INTERVIEW_SCHEDULED",
                entity_type="Interview",
                entity_id=interview.interview_id,
                target_entity_name=interview.interview_title,
                description=(
                    f"Scheduled interview "
                    f"{interview.interview_title or interview.interview_id}"
                ),
                metadata={"application_id": application_id},
                commit=False,
            )
            await InterviewService._commit_transaction(session)
        except Exception:
            await InterviewService._rollback_transaction(session)
            raise

        resume_status = await InterviewService._send_interview_notifications(
            session=session,
            application_id=application_id,
            interview=interview,
            email_sender=EmailService.send_interview_scheduled_email,
        )

        return await InterviewService._interview_response(
            session=session,
            interview=interview,
            resume_attached=resume_status["resume_attached"],
            resume_status=resume_status["resume_status"],
        )

    @staticmethod
    async def schedule_interview_rounds(
        session: AsyncSession,
        employer_id: str,
        application_id: str,
        request,
        performed_by: str | None = None,
    ):
        if len(request.rounds) > InterviewService.MAX_INTERVIEW_ROUNDS:
            raise HTTPException(
                status_code=400,
                detail="A maximum of 20 interview rounds is allowed.",
            )
        if session is not None and hasattr(session, "execute"):
            active_round_count = await InterviewRepo.count_active_by_application(
                session=session,
                application_id=application_id,
            )
            if active_round_count + len(request.rounds) > InterviewService.MAX_INTERVIEW_ROUNDS:
                raise HTTPException(
                    status_code=400,
                    detail="A maximum of 20 interview rounds is allowed.",
                )

        interviews = []
        for round_request in request.rounds:
            interview = await InterviewService.schedule_interview(
                session=session,
                employer_id=employer_id,
                application_id=application_id,
                request=round_request,
                performed_by=performed_by,
            )
            interviews.append(interview)

        return interviews

    @staticmethod
    async def get_interview(
        session: AsyncSession,
        employer_id: str,
        application_id: str,
    ):

        interviews = await InterviewRepo.get_by_application_for_employer(
            session=session,
            application_id=application_id,
            employer_id=employer_id,
        )

        if not interviews:
            raise HTTPException(
                status_code=404,
                detail="Interview not found or access denied.",
            )

        responses = [
            await InterviewService._interview_response(
                session=session,
                interview=interview,
            )
            for interview in interviews
        ]

        return InterviewRoundsResponse(
            interviews=responses,
            next_round_number=InterviewService._next_round_number(interviews),
        )

    @staticmethod
    async def update_interview(
        session: AsyncSession,
        employer_id: str,
        interview_id: str,
        request,
        performed_by: str | None = None,
    ):
        interview = await InterviewRepo.get_by_id_for_employer(
            session=session,
            interview_id=interview_id,
            employer_id=employer_id,
        )

        if not interview:
            raise HTTPException(
                status_code=404,
                detail="Interview not found or access denied.",
            )

    # Prevent updates after completion/cancellation
        if interview.status in ["COMPLETED", "CANCELLED"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot update a "
                    f"{interview.status.lower()} interview."
                ),
            )

        previous_values = InterviewService._interview_snapshot(interview)
        rescheduled = False
        interviewer_ids = None

        should_update_interviewers = (
            getattr(request, "interviewer_ids", None) is not None
            or getattr(request, "interviewer_emails", None) is not None
            or getattr(request, "interviewers", None) is not None
        )

        if (
            request.interview_date is not None
            and request.interview_date != interview.interview_date
        ):
            interview.interview_date = request.interview_date
            rescheduled = True

        if (
            request.interview_time is not None
            and request.interview_time != interview.interview_time
        ):
            interview.interview_time = request.interview_time
            rescheduled = True

        if request.interview_round is not None:
            interview.interview_round = InterviewService._schema_value(
                request.interview_round
            )

        if request.interview_title is not None:
            interview.interview_title = request.interview_title

        if request.round_number is not None:
            duplicate = await InterviewRepo.get_duplicate_interview(
                session=session,
                application_id=interview.application_id,
                interview_date=interview.interview_date,
                interview_time=interview.interview_time,
                round_number=request.round_number,
            )
            if (
                duplicate
                and duplicate.interview_id != interview.interview_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "An interview already exists for this round number."
                    ),
                )
            interview.round_number = request.round_number

        if request.mode is not None:
            interview.mode = InterviewService._schema_value(request.mode)

        if request.meeting_link is not None:
            interview.meeting_link = str(request.meeting_link)

        if request.end_time is not None:
            interview.end_time = request.end_time
            rescheduled = True

        if request.timezone is not None:
            interview.timezone = request.timezone

        if request.interview_location is not None:
            interview.interview_location = request.interview_location

        if request.interviewer_name is not None:
            interview.interviewer_name = request.interviewer_name

        if request.remarks is not None:
            interview.remarks = request.remarks

        if interview.end_time is not None and interview.end_time <= interview.interview_time:
            raise HTTPException(
                status_code=400,
                detail="End time must be after start time.",
            )

        duplicate = await InterviewRepo.get_duplicate_interview(
            session=session,
            application_id=interview.application_id,
            interview_date=interview.interview_date,
            interview_time=interview.interview_time,
            round_number=interview.round_number,
        )
        if duplicate and duplicate.interview_id != interview.interview_id:
            detail = "An interview already exists for the selected date and time."
            if interview.round_number is not None:
                detail = "An interview already exists for this round number."
            raise HTTPException(
                status_code=400,
                detail=detail,
            )

    # Only allow valid status changes
        if request.status is not None:
            interview.status = request.status.value
            if interview.status == "COMPLETED" and interview.completed_at is None:
                interview.completed_at = utc_now_naive()

    # Automatically mark as rescheduled
        if rescheduled:
            interview.status = "RESCHEDULED"

        try:
            if should_update_interviewers:
                interviewer_ids = await InterviewService._resolve_interviewers(
                    session=session,
                    interviewer_ids=getattr(request, "interviewer_ids", None),
                    interviewer_emails=getattr(request, "interviewer_emails", None),
                    interviewers=getattr(request, "interviewers", None),
                )

            interview = await InterviewService._update_interview_record(
                session=session,
                interview=interview,
            )

            if interviewer_ids is not None:
                await InterviewService._replace_interviewers(
                    session=session,
                    interview=interview,
                    interviewer_ids=interviewer_ids,
                )

            await InterviewService._record_history(
                session=session,
                interview=interview,
                employer_id=employer_id,
                performed_by=performed_by,
                action="RESCHEDULED" if rescheduled else "UPDATED",
                previous_values=previous_values,
                new_values=InterviewService._interview_snapshot(interview),
            )
            await InterviewService._commit_transaction(session)
        except Exception:
            await InterviewService._rollback_transaction(session)
            raise

        resume_status = await InterviewService._send_interview_notifications(
            session=session,
            application_id=interview.application_id,
            interview=interview,
            email_sender=(
                EmailService.send_interview_rescheduled_email
                if rescheduled
                else EmailService.send_interview_rescheduled_email
            ),
            notification_action="rescheduled" if rescheduled else "updated",
        )

        return await InterviewService._interview_response(
            session=session,
            interview=interview,
            resume_attached=resume_status["resume_attached"],
            resume_status=resume_status["resume_status"],
        )

    @staticmethod
    async def cancel_interview(
        session: AsyncSession,
        employer_id: str,
        interview_id: str,
        performed_by: str | None = None,
    ):
        interview = await InterviewRepo.get_by_id_for_employer(
            session=session,
            interview_id=interview_id,
            employer_id=employer_id,
        )

        if not interview:
            raise HTTPException(
                status_code=404,
                detail="Interview not found or access denied.",
            )

        if interview.status == "CANCELLED":
            raise HTTPException(
                status_code=400,
                detail="Interview is already cancelled.",
            )

        if interview.status == "COMPLETED":
            raise HTTPException(
                status_code=400,
                detail="Completed interviews cannot be cancelled.",
            )

        previous_values = InterviewService._interview_snapshot(interview)

        interview = await InterviewRepo.update_status(
            session=session,
            interview=interview,
            status="CANCELLED",
        )

        await InterviewService._record_history(
            session=session,
            interview=interview,
            employer_id=employer_id,
            performed_by=performed_by,
            action="CANCELLED",
            previous_values=previous_values,
            new_values=InterviewService._interview_snapshot(interview),
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=performed_by,
            actor_role="EMPLOYER",
            action="INTERVIEW_CANCELLED",
            entity_type="Interview",
            entity_id=interview.interview_id,
            target_entity_name=interview.interview_title,
            description=f"Cancelled interview {interview.interview_title or interview.interview_id}",
            metadata={"application_id": interview.application_id},
        )

        await InterviewService._send_interview_notifications(
            session=session,
            application_id=interview.application_id,
            interview=interview,
            email_sender=EmailService.send_interview_cancelled_email,
            notification_action="cancelled",
        )

        return await InterviewService._interview_response(
            session=session,
            interview=interview,
        )
        
    @staticmethod
    async def complete_interview(
        session: AsyncSession,
        employer_id: str,
        interview_id: str,
        performed_by: str | None = None,
    ):
        interview = await InterviewRepo.get_by_id_for_employer(
            session=session,
            interview_id=interview_id,
            employer_id=employer_id,
        )

        if not interview:
            raise HTTPException(
                status_code=404,
                detail="Interview not found",
            )

        if interview.status == "COMPLETED":
            raise HTTPException(
                status_code=400,
                detail="Interview is already completed.",
            )

        if interview.status == "CANCELLED":
            raise HTTPException(
                status_code=400,
                detail="Cancelled interviews cannot be completed.",
            )

        previous_values = InterviewService._interview_snapshot(interview)

        interview = await InterviewRepo.update_status(
            session=session,
            interview=interview,
            status="COMPLETED",
        )

        await InterviewService._record_history(
            session=session,
            interview=interview,
            employer_id=employer_id,
            performed_by=performed_by,
            action="COMPLETED",
            previous_values=previous_values,
            new_values=InterviewService._interview_snapshot(interview),
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=performed_by,
            actor_role="EMPLOYER",
            action="INTERVIEW_COMPLETED",
            entity_type="Interview",
            entity_id=interview.interview_id,
            target_entity_name=interview.interview_title,
            description=f"Completed interview {interview.interview_title or interview.interview_id}",
            metadata={"application_id": interview.application_id},
        )
        details = None
        if session is not None and hasattr(session, "execute"):
            details = await ShortlistedCandidatesRepo.get_interview_email_details(
                session=session,
                application_id=interview.application_id,
            )
        if details:
            candidate_user_id = details[3]
            job_title = details[8] or "N/A"
            interviewer_rows = (
                await InterviewInterviewerRepo.get_interviewer_emails(
                    session=session,
                    interview_id=interview.interview_id,
                )
            )
            await InterviewService._create_interview_notifications(
                session=session,
                interview=interview,
                candidate_user_id=(
                    str(candidate_user_id) if candidate_user_id else None
                ),
                interviewer_user_ids=[
                    str(tuple(row)[0])
                    for row in interviewer_rows
                    if len(tuple(row)) >= 4 and tuple(row)[0]
                ],
                action="completed",
                job_title=job_title,
            )

        return await InterviewService._interview_response(
            session=session,
            interview=interview,
        )
    
    @staticmethod
    async def mark_no_show(
        session: AsyncSession,
        employer_id: str,
        interview_id: str, 
        performed_by: str | None = None,
    ):
        interview = await InterviewRepo.get_by_id_for_employer(
            session=session,
            interview_id=interview_id,
            employer_id=employer_id,
        )

        if not interview:
            raise HTTPException(
                status_code=404,
                detail="Interview not found",
            )

        if interview.status == "NO_SHOW":
            raise HTTPException(
                status_code=400,
                detail="Interview is already marked as No Show.",
            )

        if interview.status == "COMPLETED":
            raise HTTPException(
                status_code=400,
                detail="Completed interviews cannot be marked as No Show.",
            )

        if interview.status == "CANCELLED":
            raise HTTPException(
                status_code=400,
                detail="Cancelled interviews cannot be marked as No Show.",
            )

        previous_values = InterviewService._interview_snapshot(interview)

        interview = await InterviewRepo.update_status(
            session=session,
            interview=interview,
            status="NO_SHOW",
        )

        await InterviewService._record_history(
            session=session,
            interview=interview,
            employer_id=employer_id,
            performed_by=performed_by,
            action="NO_SHOW",
            previous_values=previous_values,
            new_values=InterviewService._interview_snapshot(interview),
        )
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=performed_by,
            actor_role="EMPLOYER",
            action="INTERVIEW_NO_SHOW",
            entity_type="Interview",
            entity_id=interview.interview_id,
            target_entity_name=interview.interview_title,
            description=f"Marked interview no-show {interview.interview_title or interview.interview_id}",
            metadata={"application_id": interview.application_id},
        )

        return await InterviewService._interview_response(
            session=session,
            interview=interview,
        )

    @staticmethod
    async def list_interviewers(
        session: AsyncSession,
        search: str | None,
        page: int,
        page_size: int,
    ) -> InterviewerLookupResponse:
        if not hasattr(session, "execute"):
            total, rows = await InterviewInterviewerRepo.list_active_interviewers(
                session=session,
                search=search,
                page=page,
                page_size=page_size,
            )
            items = []
            for row in rows:
                values = tuple(row)
                if len(values) >= 6:
                    user_id, first_name, last_name, email, role_code, status = values[:6]
                    name = (
                        f"{first_name or ''} {last_name or ''}".strip()
                        or email
                        or str(user_id)
                    )
                    items.append(
                        InterviewerLookupItem(
                            id=str(user_id),
                            user_id=str(user_id),
                            name=name,
                            email=email,
                            role=role_code,
                            status=status,
                        )
                    )
            return InterviewerLookupResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
            )

        result = await InterviewerService.list_interviewers(
            session=session,
            search=search,
            page=page,
            page_size=page_size,
        )
        return InterviewerLookupResponse(
            items=[
                InterviewerLookupItem(**item.model_dump())
                for item in result.items
            ],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    @staticmethod
    def _interview_snapshot(interview: Interview) -> dict:
        return {
            "interview_id": interview.interview_id,
            "application_id": interview.application_id,
            "interview_title": interview.interview_title,
            "round_number": interview.round_number,
            "interview_round": interview.interview_round,
            "interview_date": (
                interview.interview_date.isoformat()
                if interview.interview_date
                else None
            ),
            "interview_time": (
                interview.interview_time.isoformat()
                if interview.interview_time
                else None
            ),
            "end_time": (
                interview.end_time.isoformat()
                if interview.end_time
                else None
            ),
            "timezone": interview.timezone,
            "mode": interview.mode,
            "meeting_link": interview.meeting_link,
            "interview_location": interview.interview_location,
            "interviewer_name": interview.interviewer_name,
            "status": interview.status,
            "remarks": interview.remarks,
            "completed_at": (
                interview.completed_at.isoformat()
                if getattr(interview, "completed_at", None)
                else None
            ),
        }

    @staticmethod
    def _next_round_number(interviews: list[Interview]) -> int:
        max_round_number = max(
            (
                interview.round_number
                for interview in interviews
                if interview.round_number is not None
            ),
            default=0,
        )
        return max_round_number + 1

    @staticmethod
    async def _record_history(
        *,
        session: AsyncSession,
        interview: Interview,
        employer_id: str,
        performed_by: str | None,
        action: str,
        previous_values: dict | None,
        new_values: dict | None,
    ) -> None:
        history = InterviewHistory(
            interview_id=interview.interview_id,
            application_id=interview.application_id,
            employer_id=employer_id,
            performed_by=performed_by,
            action=action,
            previous_values=previous_values,
            new_values=new_values,
        )

        await InterviewHistoryRepo.create_history(
            session=session,
            history=history,
            commit=False if InterviewService._has_real_transaction(session) else True,
        )

    @staticmethod
    async def _send_interview_notifications(
        *,
        session: AsyncSession,
        application_id: str,
        interview: Interview,
        email_sender,
        notification_action: str = "scheduled",
    ) -> dict:
        details = await ShortlistedCandidatesRepo.get_interview_email_details(
            session=session,
            application_id=application_id,
        )

        if not details:
            logger.warning(
                "Interview email details not found for application_id=%s",
                application_id,
            )
            return {
                "resume_attached": False,
                "resume_status": InterviewService.RESUME_STATUS_NOT_PROVIDED,
            }

        (
            first_name,
            last_name,
            candidate_email,
            candidate_user_id,
            candidate_id,
            company_name,
            employer_email,
            employer_user_id,
            job_title,
            resume_id,
        ) = details

        payload = InterviewService._build_interview_email_payload(
            candidate_name=(
                f"{first_name or ''} {last_name or ''}".strip()
                or "Candidate"
            ),
            company_name=company_name or "N/A",
            employer_name=company_name or "N/A",
            job_title=job_title or "N/A",
            interview=interview,
        )

        interviewer_rows = (
            await InterviewInterviewerRepo.get_interviewer_emails(
                session=session,
                interview_id=interview.interview_id,
            )
        )

        attendees = [
            InterviewService._interviewer_email_from_row(row)
            for row in interviewer_rows
            if InterviewService._interviewer_email_from_row(row)
        ]
        if candidate_email:
            attendees.append(candidate_email)

        calendar_invite = InterviewService._build_ics_attachment(
            payload=payload,
            interview=interview,
            organizer=employer_email,
            attendees=attendees,
        )

        resume_attachment = None
        resume_status = InterviewService.RESUME_STATUS_NOT_PROVIDED
        if notification_action != "cancelled":
            resume_attachment = await InterviewService._get_resume_attachment(
                session=session,
                application_id=application_id,
                interview_id=interview.interview_id,
            )
            if resume_attachment:
                resume_status = InterviewService.RESUME_STATUS_ATTACHED
            elif resume_id:
                resume_status = InterviewService.RESUME_STATUS_UNAVAILABLE

        sent_to = set()
        await InterviewService._send_interview_email(
            email_sender=email_sender,
            to_email=candidate_email,
            payload=payload,
            include_remarks=False,
            sent_to=sent_to,
            interview_id=interview.interview_id,
            calendar_invite=calendar_invite,
            resume_attachment=resume_attachment,
        )

        for row in interviewer_rows:
            interviewer_id, interviewer_name, to_email = (
                InterviewService._interviewer_contact_from_row(row)
            )
            interviewer_payload = {
                **payload,
                "candidate_name": (
                    f"{first_name or ''} {last_name or ''}".strip()
                    or "Candidate"
                ),
                "interviewer": interviewer_name or payload["interviewer"],
            }
            await InterviewService._send_interview_email(
                email_sender=email_sender,
                to_email=to_email,
                payload=interviewer_payload,
                include_remarks=False,
                sent_to=sent_to,
                interview_id=interview.interview_id,
                calendar_invite=calendar_invite,
            )

        await InterviewService._create_interview_notifications(
            session=session,
            interview=interview,
            candidate_user_id=str(candidate_user_id) if candidate_user_id else None,
            interviewer_user_ids=[
                str(tuple(row)[0])
                for row in interviewer_rows
                if len(tuple(row)) >= 4 and tuple(row)[0]
            ],
            action=notification_action,
            job_title=job_title or "N/A",
        )

        return {
            "resume_attached": bool(resume_attachment),
            "resume_status": resume_status,
        }

    @staticmethod
    async def _send_interview_email(
        *,
        email_sender,
        to_email: str | None,
        payload: dict,
        include_remarks: bool,
        sent_to: set,
        interview_id: str,
        calendar_invite: tuple[str, bytes, str] | None = None,
        resume_attachment: tuple[str, bytes, str] | None = None,
    ) -> None:
        if not to_email or to_email in sent_to:
            return

        try:
            await email_sender(
                to_email=to_email,
                include_remarks=include_remarks,
                attachments=[
                    attachment
                    for attachment in (
                        calendar_invite,
                        resume_attachment,
                    )
                    if attachment
                ],
                **payload,
            )
            sent_to.add(to_email)
        except Exception:
            logger.exception(
                "Failed to send interview email for "
                "interview_id=%s to_email=%s",
                interview_id,
                to_email,
            )

    @staticmethod
    async def _validate_interviewer_ids(
        *,
        session: AsyncSession,
        interviewer_ids,
    ):
        return await InterviewService._resolve_interviewers(
            session=session,
            interviewer_ids=interviewer_ids,
            interviewer_emails=None,
            interviewers=None,
        )

    @staticmethod
    async def _resolve_interviewers(
        *,
        session: AsyncSession,
        interviewer_ids,
        interviewer_emails,
        interviewers=None,
    ) -> list[str]:
        unique_ids: list[str] = []
        if interviewer_ids:
            unique_ids = list(dict.fromkeys(str(value) for value in interviewer_ids))
            if len(unique_ids) != len(interviewer_ids):
                raise HTTPException(
                    status_code=400,
                    detail="Duplicate interviewers are not allowed in the same round.",
                )

        email_to_name: dict[str, str] = {}
        if interviewer_emails:
            for email in interviewer_emails:
                normalized = str(email).strip().lower()
                email_to_name.setdefault(normalized, normalized.split("@")[0])

        if interviewers:
            for interviewer in interviewers:
                email_to_name[interviewer.email] = interviewer.name

        if not unique_ids and not email_to_name:
            if session is None:
                return []
            raise HTTPException(
                status_code=400,
                detail="At least one interviewer is required.",
            )

        if email_to_name and interviewers is None and not hasattr(session, "execute"):
            normalized_emails = list(email_to_name.keys())
            email_users = await InterviewInterviewerRepo.get_active_interviewer_users_by_emails(
                session=session,
                emails=normalized_emails,
            )
            users_by_email = {
                user.email.lower(): user
                for user in email_users
                if getattr(user, "email", None)
            }
            if set(users_by_email) != set(normalized_emails):
                raise HTTPException(
                    status_code=400,
                    detail=InterviewService.INVALID_INTERVIEWER_EMAILS_MESSAGE,
                )
            return [
                users_by_email[email].user_id
                for email in normalized_emails
            ]

        if unique_ids:
            for interviewer_id in unique_ids:
                interviewer = await InterviewerRepo.get_by_id(
                    session=session,
                    interviewer_id=interviewer_id,
                )
                if not interviewer:
                    raise HTTPException(
                        status_code=400,
                        detail="One or more interviewers are invalid.",
                    )

        resolved_email_ids: list[str] = []
        if email_to_name:
            normalized_emails = list(email_to_name.keys())
            existing_interviewers = await InterviewerRepo.get_by_emails(
                session=session,
                emails=normalized_emails,
            )
            interviewers_by_email = {
                interviewer.email.lower(): interviewer
                for interviewer in existing_interviewers
            }
            for email in normalized_emails:
                interviewer = interviewers_by_email.get(email)
                if interviewer is None:
                    interviewer = Interviewer(
                        name=email_to_name[email],
                        email=email,
                    )
                    interviewer = await InterviewerRepo.create(
                        session=session,
                        interviewer=interviewer,
                    )
                    interviewers_by_email[email] = interviewer
                resolved_email_ids.append(interviewer.id)

        merged_ids = list(dict.fromkeys([*unique_ids, *resolved_email_ids]))
        if not merged_ids:
            raise HTTPException(
                status_code=400,
                detail="At least one interviewer is required.",
            )

        return merged_ids

    @staticmethod
    async def _validate_interviewers(
        *,
        session: AsyncSession,
        interviewer_ids,
        interviewer_emails,
    ) -> list[str]:
        return await InterviewService._resolve_interviewers(
            session=session,
            interviewer_ids=interviewer_ids,
            interviewer_emails=interviewer_emails,
            interviewers=None,
        )

    @staticmethod
    def _schema_value(value):
        return getattr(value, "value", value)

    @staticmethod
    async def _validate_round_limit(
        *,
        session: AsyncSession,
        application_id: str,
    ) -> None:
        if session is None or not hasattr(session, "execute"):
            return

        active_round_count = await InterviewRepo.count_active_by_application(
            session=session,
            application_id=application_id,
        )
        if active_round_count >= InterviewService.MAX_INTERVIEW_ROUNDS:
            raise HTTPException(
                status_code=400,
                detail="A maximum of 20 interview rounds is allowed.",
            )

    @staticmethod
    def _has_real_transaction(session: AsyncSession | None) -> bool:
        return hasattr(session, "commit") and hasattr(session, "rollback")

    @staticmethod
    async def _commit_transaction(session: AsyncSession | None) -> None:
        if InterviewService._has_real_transaction(session):
            await session.commit()

    @staticmethod
    async def _rollback_transaction(session: AsyncSession | None) -> None:
        if InterviewService._has_real_transaction(session):
            await session.rollback()

    @staticmethod
    async def _create_interview_record(
        *,
        session: AsyncSession,
        interview: Interview,
    ) -> Interview:
        return await InterviewRepo.create_interview(
            session=session,
            interview=interview,
            commit=False,
        ) if InterviewService._has_real_transaction(session) else await InterviewRepo.create_interview(
            session=session,
            interview=interview,
        )

    @staticmethod
    async def _update_interview_record(
        *,
        session: AsyncSession,
        interview: Interview,
    ) -> Interview:
        return await InterviewRepo.update_interview(
            session=session,
            interview=interview,
            commit=False,
        ) if InterviewService._has_real_transaction(session) else await InterviewRepo.update_interview(
            session=session,
            interview=interview,
        )

    @staticmethod
    async def _update_application_status(
        *,
        session: AsyncSession,
        application_id: str,
        status: str,
    ):
        if InterviewService._has_real_transaction(session):
            return await ShortlistedCandidatesRepo.update_status(
                session=session,
                application_id=application_id,
                status=status,
                commit=False,
            )
        return await ShortlistedCandidatesRepo.update_status(
            session=session,
            application_id=application_id,
            status=status,
        )

    @staticmethod
    async def _assigned_interviewers(
        *,
        session: AsyncSession,
        interview_id: str,
    ) -> list[AssignedInterviewerResponse]:
        if session is None:
            return []

        rows = await InterviewInterviewerRepo.get_assigned_interviewers(
            session=session,
            interview_id=interview_id,
        )

        assigned_by_id: dict[str, AssignedInterviewerResponse] = {}
        for row in rows:
            interviewer_id, name, email = (
                InterviewService._interviewer_contact_from_row(row)
            )
            values = tuple(row)
            role = values[4] if len(values) >= 5 else None
            key = str(interviewer_id)
            if key in assigned_by_id:
                continue
            assigned_by_id[key] = AssignedInterviewerResponse(
                id=key,
                user_id=key,
                name=name or email or key,
                email=email,
                role=role,
            )

        return list(assigned_by_id.values())

    @staticmethod
    async def _interview_response(
        *,
        session: AsyncSession,
        interview: Interview,
        resume_attached: bool = False,
        resume_status: str = "not_provided",
    ) -> InterviewResponse:
        return InterviewResponse(
            interview_id=interview.interview_id,
            application_id=interview.application_id,
            interview_title=interview.interview_title,
            round_number=interview.round_number,
            interview_round=interview.interview_round,
            interview_date=interview.interview_date,
            interview_time=interview.interview_time,
            start_time=interview.interview_time,
            end_time=interview.end_time,
            timezone=interview.timezone,
            mode=interview.mode,
            meeting_link=interview.meeting_link,
            interview_location=interview.interview_location,
            interviewer_name=interview.interviewer_name,
            assigned_interviewers=await InterviewService._assigned_interviewers(
                session=session,
                interview_id=interview.interview_id,
            ),
            status=interview.status,
            remarks=interview.remarks,
            created_at=(
                interview.created_at.isoformat()
                if interview.created_at
                else None
            ),
            updated_at=(
                interview.updated_at.isoformat()
                if interview.updated_at
                else None
            ),
            completed_at=(
                interview.completed_at.isoformat()
                if getattr(interview, "completed_at", None)
                else None
            ),
            resume_attached=resume_attached,
            resume_status=resume_status,
        )

    @staticmethod
    async def _replace_interviewers(
        *,
        session: AsyncSession,
        interview: Interview,
        interviewer_ids,
    ) -> None:
        if interviewer_ids is None:
            return
        if session is None and not interviewer_ids:
            return

        await InterviewInterviewerRepo.replace_interviewers(
            session=session,
            interview_id=interview.interview_id,
            interviewer_ids=interviewer_ids,
        )

        if interviewer_ids:
            rows = await InterviewInterviewerRepo.get_assigned_interviewers(
                session=session,
                interview_id=interview.interview_id,
            )
            interview.interviewer_name = ", ".join(
                name or email or interviewer_id
                for interviewer_id, name, email in (
                    InterviewService._interviewer_contact_from_row(row)
                    for row in rows
                )
            )

            await InterviewService._update_interview_record(
                session=session,
                interview=interview,
            )

    @staticmethod
    def _build_interview_email_payload(
        *,
        candidate_name: str,
        company_name: str,
        employer_name: str,
        job_title: str,
        interview: Interview,
    ) -> dict:
        return {
            "candidate_name": candidate_name,
            "interview_title": (
                interview.interview_title
                or f"{job_title} Interview"
            ),
            "company_name": company_name,
            "employer_name": employer_name,
            "job_title": job_title,
            "interview_round": interview.interview_round,
            "interview_date": (
                interview.interview_date.isoformat()
                if interview.interview_date
                else "N/A"
            ),
            "interview_time": (
                interview.interview_time.strftime("%H:%M")
                if interview.interview_time
                else "N/A"
            ),
            "start_time": (
                interview.interview_time.strftime("%H:%M")
                if interview.interview_time
                else "N/A"
            ),
            "end_time": (
                interview.end_time.strftime("%H:%M")
                if interview.end_time
                else "N/A"
            ),
            "timezone": interview.timezone or "UTC",
            "mode": interview.mode,
            "meeting_link_or_location": (
                interview.meeting_link
                or interview.interview_location
                or "N/A"
            ),
            "interviewer": interview.interviewer_name or "N/A",
            "remarks": interview.remarks or "N/A",
        }

    @staticmethod
    def _interviewer_email_from_row(row) -> str | None:
        values = tuple(row)
        if len(values) >= 4:
            return values[3]
        if len(values) >= 3:
            return values[2]
        return None

    @staticmethod
    def _interviewer_contact_from_row(row) -> tuple[str, str, str | None]:
        values = tuple(row)
        if len(values) >= 4:
            interviewer_id = str(values[0])
            name = (
                f"{values[1] or ''} {values[2] or ''}".strip()
                or values[3]
                or interviewer_id
            )
            return interviewer_id, name, values[3]

        interviewer_id = str(values[0])
        name = values[1] or values[2] or interviewer_id
        email = values[2] if len(values) >= 3 else None
        return interviewer_id, name, email

    @staticmethod
    def _build_ics_attachment(
        *,
        payload: dict,
        interview: Interview,
        organizer: str | None,
        attendees: list[str],
    ) -> tuple[str, bytes, str] | None:
        if not interview.interview_date or not interview.interview_time:
            return None

        start_dt = datetime.combine(
            interview.interview_date,
            interview.interview_time,
        )
        end_dt = datetime.combine(
            interview.interview_date,
            interview.end_time or interview.interview_time,
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uid = f"{interview.interview_id}@nmk-jobportal"

        def fmt(value: datetime) -> str:
            return value.strftime("%Y%m%dT%H%M%S")

        def esc(value: str | None) -> str:
            return (value or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//NMK Job Portal//Interview Scheduling//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:REQUEST",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID={esc(payload['timezone'])}:{fmt(start_dt)}",
            f"DTEND;TZID={esc(payload['timezone'])}:{fmt(end_dt)}",
            f"SUMMARY:{esc(payload['interview_title'])}",
            f"LOCATION:{esc(interview.meeting_link or interview.interview_location)}",
            (
                "DESCRIPTION:"
                f"{esc(payload['candidate_name'])} | "
                f"{esc(payload['company_name'])} | "
                f"{esc(payload['job_title'])} | "
                f"{esc(payload['interview_round'])} | "
                f"{esc(payload['remarks'])}"
            ),
        ]
        if organizer:
            lines.append(f"ORGANIZER:MAILTO:{organizer}")
        for attendee in attendees:
            lines.append(f"ATTENDEE:MAILTO:{attendee}")
        lines.extend(["END:VEVENT", "END:VCALENDAR"])
        return (
            "interview-invite.ics",
            "\r\n".join(lines).encode("utf-8"),
            "text/calendar",
        )

    @staticmethod
    async def _get_resume_attachment(
        *,
        session: AsyncSession,
        application_id: str,
        interview_id: str | None = None,
    ) -> tuple[str, bytes, str] | None:
        try:
            resume = await ShortlistedCandidatesRepo.get_candidate_resume_for_interview(
                session=session,
                application_id=application_id,
            )
            if not resume:
                logger.info(
                    "No application resume available for application_id=%s interview_id=%s",
                    application_id,
                    interview_id,
                )
                return None

            filename = resume.file_name or "candidate-resume"
            if resume.blob_ref:
                content, content_type = s3_service.fetch_object_bytes(
                    resume.blob_ref
                )
                return (
                    filename,
                    content,
                    content_type or "application/octet-stream",
                )

            if resume.file_path and os.path.exists(resume.file_path):
                with open(resume.file_path, "rb") as resume_file:
                    content = resume_file.read()
                return (
                    filename,
                    content,
                    mimetypes.guess_type(filename)[0]
                    or "application/octet-stream",
                )

            logger.warning(
                "Candidate resume file not found for application_id=%s interview_id=%s",
                application_id,
                interview_id,
            )
        except Exception:
            logger.exception(
                "Failed to attach candidate resume for application_id=%s interview_id=%s",
                application_id,
                interview_id,
            )

        return None

    @staticmethod
    async def _create_interview_notifications(
        *,
        session: AsyncSession,
        interview: Interview,
        candidate_user_id: str | None,
        interviewer_user_ids: list[str],
        action: str,
        job_title: str,
    ) -> None:
        normalized_action = action.lower()
        title_by_action = {
            "scheduled": NotificationTitle.INTERVIEW,
            "updated": "Interview Updated",
            "rescheduled": NotificationTitle.INTERVIEW_RESCHEDULED,
            "cancelled": NotificationTitle.INTERVIEW_CANCELLED,
            "completed": NotificationTitle.INTERVIEW_COMPLETED,
        }
        type_by_action = {
            "scheduled": NotificationType.INTERVIEW_SCHEDULED,
            "updated": NotificationType.INTERVIEW_RESCHEDULED,
            "rescheduled": NotificationType.INTERVIEW_RESCHEDULED,
            "cancelled": NotificationType.INTERVIEW_CANCELLED,
            "completed": NotificationType.INTERVIEW_COMPLETED,
        }
        title = title_by_action.get(normalized_action, NotificationTitle.INTERVIEW)
        notification_type = type_by_action.get(
            normalized_action,
            NotificationType.INTERVIEW,
        )

        message = (
            f"Your {job_title} interview round "
            f"'{interview.interview_round}' has been {normalized_action}."
        )
        recipients = []
        if candidate_user_id:
            recipients.append(candidate_user_id)
        recipients.extend(interviewer_user_ids)

        for recipient_id in dict.fromkeys(recipients):
            await NotificationService.create_notification(
                session=session,
                recipient_id=recipient_id,
                title=title,
                message=message,
                notification_type=notification_type,
                reference_type=ReferenceType.INTERVIEW,
                reference_id=interview.interview_id,
                entity_type=ReferenceType.INTERVIEW,
                entity_id=interview.interview_id,
                target_route=f"/interviews/{interview.interview_id}",
                metadata={
                    "application_id": interview.application_id,
                    "interview_id": interview.interview_id,
                    "job_title": job_title,
                    "interview_date": (
                        interview.interview_date.isoformat()
                        if interview.interview_date
                        else None
                    ),
                    "interview_time": (
                        interview.interview_time.strftime("%H:%M")
                        if interview.interview_time
                        else None
                    ),
                    "timezone": interview.timezone,
                    "status": getattr(interview, "status", None),
                },
                event_key=(
                    f"interview:{normalized_action}:{recipient_id}:"
                    f"{interview.interview_id}:{getattr(interview, 'updated_at', None)}"
                ),
            )
