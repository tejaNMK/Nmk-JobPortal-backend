from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID
from app.utils.utc import utc_now_naive

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.employer_model.candidate_invitation import CandidateInvitation
from app.model.authentication.users import Users
from app.repository.employer_repository.invitations_repo import InvitationsRepository
from app.repository.employer_repository.job_repo import JobRepository
from app.utils.job_time import posted_display_date, utc_now_naive
from app.repository.profile_repo import EmployerProfileRepository
from app.service.subscription.subscription_validator import SubscriptionValidator
from app.utils.image_urls import resolve_profile_image_url
from app.constants.notification_constants import (
    NotificationMessage,
    NotificationTitle,
    NotificationType,
    ReferenceType,
)
from app.schema.invitations import (
    SendInvitationRequest,
    RespondInvitationRequest,
    CandidateInvitationListResponse,
    CandidateInvitationListItem,
    CandidateInvitationDetailsResponse,
    CandidateInvitationEmployerDetails,
    CandidateInvitationRecruiterDetails,
    CandidateInvitationJobSummary,
    InvitationResponse,
    EmployerInvitationListResponse,
    EmployerInvitationListItem,
    ActiveJobSummary,
    EmployerActiveJobsResponse,
)
from app.service.notification_service import NotificationService


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


def _top_skills(profile) -> list[str]:
    summary = getattr(profile, "skills_summary", None)
    if not summary:
        return []
    return [part.strip() for part in str(summary).split(",") if part.strip()][:5]



class EmployerInvitationsService:
    @staticmethod
    async def _get_employer_id_from_payload(*, session: AsyncSession, payload: dict) -> str:
        user_id_raw = payload.get("user_id")
        if not user_id_raw:
            raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
        employer = await EmployerProfileRepository.get_by_user_id(
            session=session,
            user_id=UUID(str(user_id_raw)),
        )
        if not employer:
            raise HTTPException(status_code=404, detail="Employer profile not found")
        return str(employer.id)


    @staticmethod
    async def send_invitation(
        *,
        session: AsyncSession,
        payload: dict,
        candidate_id: str,
        request: SendInvitationRequest,
        message: str,
    ) -> CandidateInvitation:
        employer_user_id = payload.get("user_id")
        employer_profile = await EmployerProfileRepository.get_by_user_id(
            session=session,
            user_id=UUID(str(employer_user_id)),
        )
        if not employer_profile:
            raise HTTPException(status_code=403, detail="Employer profile not found")
        validator = SubscriptionValidator(
            session=session,
            user_id=employer_user_id,
            role="EMPLOYER",
        )
        await validator.require_feature("candidate_invitations")
        await validator.ensure_limit_available(
            "candidate_invitations_per_week",
            period="week",
        )

        # Candidate must exist and be visible/public
        candidate_profile = await session.execute(
            select(CandidateProfile)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                # Gated by the "Recruiter search" toggle only — independent
                # of the candidate's "Public link" toggle.
                CandidateProfile.searchable_flag.is_(True),
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )
        candidate_profile = candidate_profile.scalar_one_or_none()
        if not candidate_profile:
            raise HTTPException(status_code=404, detail="Candidate not found or not visible")

        job = await InvitationsRepository.get_job_owned_by_employer(
            session,
            employer_id=str(employer_profile.id),
            job_id=request.job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status not in JobRepository.OPEN_STATUSES:
            raise HTTPException(status_code=400, detail="Job is not active/open")

        is_duplicate = await InvitationsRepository.has_duplicate_active_invitation(
            session,
            employer_id=str(employer_profile.id),
            candidate_id=candidate_id,
            job_id=request.job_id,
        )
        if is_duplicate:
            raise HTTPException(status_code=409, detail="Duplicate active invitation")

        invitation = CandidateInvitation(
            employer_id=str(employer_profile.id),
            candidate_id=candidate_id,
            job_id=request.job_id,
            custom_message=message,
            status="PENDING",
            invited_at=utc_now_naive(),
            viewed_at=None,
            responded_at=None,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )

        created = await InvitationsRepository.create_invitation(session, invitation=invitation)
        await validator.consume_limit(
            "candidate_invitations_per_week",
            period="week",
        )
        return created


    @staticmethod
    async def list_invitations(
        *,
        session: AsyncSession,
        payload: dict,
        filters,
    ) -> EmployerInvitationListResponse:
        employer_id = await EmployerInvitationsService._get_employer_id_from_payload(
            session=session,
            payload=payload,
        )
        total, rows = await InvitationsRepository.list_employer_invitations(
            session,
            employer_id=employer_id,
            filters=filters,
        )

        items: List[EmployerInvitationListItem] = []
        for inv, profile, user, job in rows:
            items.append(
                EmployerInvitationListItem(
                    invitation_id=inv.invitation_id,
                    candidate={
                        "candidate_id": inv.candidate_id,
                        "full_name": _full_name(user),
                        "profile_photo": resolve_profile_image_url(
                            getattr(user, "profile_image_url", None)
                        ),
                        "profile_headline": profile.headline,
                        "current_designation": profile.current_company,
                        "years_of_experience": float(profile.total_experience)
                        if profile.total_experience is not None
                        else None,
                        "location": profile.current_location,
                        "top_skills": _top_skills(profile),
                        "education_summary": None,
                        "availability": profile.notice_period,
                        "profile_completion_percentage": profile.profile_completion_pct,
                        "last_updated": profile.updated_at,
                    },
                    job_title=getattr(job, "title", None),
                    status=inv.status,
                    invited_at=inv.invited_at,
                    viewed_at=inv.viewed_at,
                    responded_at=inv.responded_at,
                )
            )

        return EmployerInvitationListResponse(
            page=filters.page,
            page_size=filters.page_size,
            total_records=total,
            items=items,
        )

    @staticmethod
    async def list_active_jobs(
        *,
        session: AsyncSession,
        payload: dict,
        page: int,
        page_size: int,
    ) -> EmployerActiveJobsResponse:
        employer_id = await EmployerInvitationsService._get_employer_id_from_payload(
            session=session,
            payload=payload,
        )
        if hasattr(session, "execute"):
            await JobRepository.expire_jobs_past_deadline(
                session=session,
                employer_id=employer_id,
                now=utc_now_naive(),
            )
        total, rows = await InvitationsRepository.list_active_jobs_for_invitation(
            session,
            employer_id=employer_id,
            page=page,
            page_size=page_size,
        )
        return EmployerActiveJobsResponse(
            page=page,
            page_size=page_size,
            total_records=total,
            items=[
                ActiveJobSummary(
                    job_id=job.job_id,
                    title=job.title,
                    department=getattr(job, "team", None),
                    location=job.location,
                    employment_type=job.employment_type,
                    openings=job.no_of_openings,
                    posted_date=posted_display_date(job.created_at),
                    application_count=int(application_count or 0),
                )
                for job, application_count in rows
            ],
        )


class CandidateInvitationsService:
    PENDING_STATUS = "PENDING"
    VIEWED_STATUS = "VIEWED"
    ACCEPTED_STATUS = "ACCEPTED"
    REJECTED_STATUS = "REJECTED"
    ACTIONABLE_STATUSES = {PENDING_STATUS, VIEWED_STATUS}

    @staticmethod
    async def _notify_employer_invitation_response(
        *,
        session: AsyncSession,
        invitation_id: str,
        candidate_id: str,
        status: str,
    ) -> None:
        if not hasattr(session, "execute"):
            return

        row = await InvitationsRepository.get_invitation_notification_context(
            session,
            invitation_id=invitation_id,
            candidate_id=candidate_id,
        )
        if not row:
            return

        invitation, job, employer, candidate_user = row
        employer_user_id = getattr(employer, "user_id", None)
        if not employer_user_id:
            return

        candidate_name = _full_name(candidate_user) or "A candidate"
        job_title = getattr(job, "title", None) or "your job"
        accepted = status == CandidateInvitationsService.ACCEPTED_STATUS

        await NotificationService.create_notification(
            session=session,
            recipient_id=str(employer_user_id),
            recipient_role="ROLE_EMPLOYER",
            title=(
                NotificationTitle.INVITATION_ACCEPTED
                if accepted
                else NotificationTitle.INVITATION_REJECTED
            ),
            message=(
                NotificationMessage.INVITATION_ACCEPTED
                if accepted
                else NotificationMessage.INVITATION_REJECTED
            ).format(candidate_name=candidate_name, job_title=job_title),
            notification_type=(
                NotificationType.INVITATION_ACCEPTED
                if accepted
                else NotificationType.INVITATION_REJECTED
            ),
            reference_type=ReferenceType.INVITATION,
            reference_id=invitation.invitation_id,
            entity_type=ReferenceType.JOB,
            entity_id=invitation.job_id,
            target_route=f"/employer/invitations?candidate_id={candidate_id}",
            metadata={
                "invitation_id": invitation.invitation_id,
                "job_id": invitation.job_id,
                "job_title": job_title,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "status": status,
            },
            event_key=f"invitation:{status.lower()}:{invitation.invitation_id}",
        )

    @staticmethod
    async def _get_candidate_id_from_payload(session: AsyncSession, payload: dict) -> str:

        user_id_raw = payload.get("user_id")
        if not user_id_raw:
            raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
        res = await session.execute(
            select(CandidateProfile.candidate_id).where(
                CandidateProfile.user_id == UUID(str(user_id_raw)),
                CandidateProfile.is_deleted.is_(False),
            )
        )
        cid = res.scalar_one_or_none()
        if not cid:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return cid

    @staticmethod
    async def list_invitations(
        *,
        session: AsyncSession,
        payload: dict,
        filters,
    ) -> CandidateInvitationListResponse:
        candidate_id = await CandidateInvitationsService._get_candidate_id_from_payload(session, payload)
        total, rows = await InvitationsRepository.list_candidate_invitations(
            session,
            candidate_id=candidate_id,
            filters=filters,
        )

        items: List[CandidateInvitationListItem] = []
        for row in rows:
            row_values = tuple(row)
            inv, job, employer, employer_user = row_values[:4]
            company = row_values[4] if len(row_values) > 4 else None
            employer_name = _full_name(employer_user) or employer.company_name
            company_name = getattr(company, "company_name", None) or employer.company_name
            company_logo = (
                getattr(company, "logo_url", None)
                or getattr(company, "logo_path", None)
                or employer.company_logo_url
            )
            items.append(
                CandidateInvitationListItem(
                    invitation_id=inv.invitation_id,
                    job_id=inv.job_id,
                    company_name=company_name,
                    company_logo=company_logo,
                    employer_name=employer_name,
                    job_title=getattr(job, "title", None) if job else None,
                    job_location=getattr(job, "location", None) if job else None,
                    employment_type=getattr(job, "employment_type", None) if job else None,
                    invitation_message=inv.custom_message,
                    invited_at=inv.invited_at,
                    accepted_at=inv.accepted_at,
                    rejected_at=inv.rejected_at,
                    status=inv.status,
                )
            )


        return CandidateInvitationListResponse(
            page=filters.page,
            page_size=filters.page_size,
            total_records=total,
            items=items,
        )

    @staticmethod
    async def get_invitation_details(
        *,
        session: AsyncSession,
        payload: dict,
        invitation_id: str,
    ) -> CandidateInvitationDetailsResponse:
        candidate_id = await CandidateInvitationsService._get_candidate_id_from_payload(session, payload)
        row = await InvitationsRepository.get_candidate_invitation_details(
            session,
            invitation_id=invitation_id,
            candidate_id=candidate_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Invitation not found")

        invitation, job, employer, recruiter, company, skills = row
        if invitation.status == CandidateInvitationsService.PENDING_STATUS:
            invitation = await InvitationsRepository.mark_viewed(
                session,
                invitation=invitation,
            )
        company_name = getattr(company, "company_name", None) or employer.company_name
        company_logo = (
            getattr(company, "logo_url", None)
            or getattr(company, "logo_path", None)
            or employer.company_logo_url
        )
        employer_details = CandidateInvitationEmployerDetails(
            employer_id=str(employer.id),
            company_name=company_name,
            company_logo=company_logo,
            company_email=getattr(company, "contact_email", None) or employer.company_email,
            company_website=getattr(company, "website", None) or employer.company_website or employer.website_url,
            company_location=getattr(company, "location", None) or employer.company_location or employer.location,
        )
        return CandidateInvitationDetailsResponse(
            invitation_id=invitation.invitation_id,
            status=invitation.status,
            invitation_message=invitation.custom_message,
            invited_at=invitation.invited_at,
            viewed_at=invitation.viewed_at,
            responded_at=invitation.responded_at,
            accepted_at=invitation.accepted_at,
            rejected_at=invitation.rejected_at,
            created_at=invitation.created_at,
            employer=employer_details,
            company=employer_details,
            recruiter=CandidateInvitationRecruiterDetails(
                recruiter_id=str(getattr(recruiter, "user_id", "")) if recruiter else None,
                full_name=_full_name(recruiter) if recruiter else None,
                email=getattr(recruiter, "email", None),
                profile_photo=resolve_profile_image_url(
                    getattr(recruiter, "profile_image_url", None)
                ),
                job_title=getattr(employer, "job_title", None),
                department=getattr(employer, "department", None),
            ),
            job=CandidateInvitationJobSummary(
                job_id=job.job_id,
                job_title=job.title,
                location=job.location,
                employment_type=job.employment_type,
                work_preference=job.work_mode,
                experience_min=job.experience_min,
                experience_max=job.experience_max,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency=job.salary_currency,
                salary_period=job.salary_period,
                description=job.description,
                skills=skills,
                posted_date=job.created_at,
                application_deadline=job.application_deadline,
            ),
            job_details_url=f"/candidate/jobs/{job.job_id}",
        )

    @staticmethod
    async def _respond_invitation(
        *,
        session: AsyncSession,
        payload: dict,
        invitation_id: str,
        new_status: str,
    ) -> InvitationResponse:
        user_id_raw = payload.get("user_id")
        if new_status == CandidateInvitationsService.ACCEPTED_STATUS:
            if not user_id_raw:
                raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
            if hasattr(session, "execute"):
                await SubscriptionValidator(
                    session=session,
                    user_id=UUID(str(user_id_raw)),
                    role="CANDIDATE",
                ).require_feature("recruiters_can_contact_candidate")

        candidate_id = await CandidateInvitationsService._get_candidate_id_from_payload(session, payload)
        invitation = await InvitationsRepository.get_invitation_by_id_and_candidate(
            session,
            invitation_id=invitation_id,
            candidate_id=candidate_id,
        )

        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if invitation.status not in CandidateInvitationsService.ACTIONABLE_STATUSES:
            raise HTTPException(status_code=400, detail="Invitation is not pending")

        now = utc_now_naive()
        invitation = await InvitationsRepository.update_invitation_status(
            session,
            invitation=invitation,
            new_status=new_status,
            responded_at=now,
            accepted_at=now if new_status == CandidateInvitationsService.ACCEPTED_STATUS else None,
            rejected_at=now if new_status == CandidateInvitationsService.REJECTED_STATUS else None,
            updated_at=now,
        )
        await CandidateInvitationsService._notify_employer_invitation_response(
            session=session,
            invitation_id=invitation_id,
            candidate_id=candidate_id,
            status=new_status,
        )
        return InvitationResponse(
            invitation_id=invitation.invitation_id,
            status=invitation.status,
            job_id=invitation.job_id,
            job_details_url=f"/candidate/jobs/{invitation.job_id}",
            invited_at=invitation.invited_at,
            viewed_at=invitation.viewed_at,
            responded_at=invitation.responded_at,
            accepted_at=invitation.accepted_at,
            rejected_at=invitation.rejected_at,
            created_at=invitation.created_at,
            updated_at=invitation.updated_at,
        )

    @staticmethod
    async def accept_invitation(
        *,
        session: AsyncSession,
        payload: dict,
        invitation_id: str,
    ) -> InvitationResponse:
        return await CandidateInvitationsService._respond_invitation(
            session=session,
            payload=payload,
            invitation_id=invitation_id,
            new_status=CandidateInvitationsService.ACCEPTED_STATUS,
        )

    @staticmethod
    async def reject_invitation(
        *,
        session: AsyncSession,
        payload: dict,
        invitation_id: str,
    ) -> InvitationResponse:
        return await CandidateInvitationsService._respond_invitation(
            session=session,
            payload=payload,
            invitation_id=invitation_id,
            new_status=CandidateInvitationsService.REJECTED_STATUS,
        )

    @staticmethod
    async def respond(
        *,
        session: AsyncSession,
        payload: dict,
        invitation_id: str,
        request: RespondInvitationRequest,
    ) -> InvitationResponse:
        new_status = (
            CandidateInvitationsService.ACCEPTED_STATUS
            if request.status == "accepted"
            else CandidateInvitationsService.REJECTED_STATUS
        )
        return await CandidateInvitationsService._respond_invitation(
            session=session,
            payload=payload,
            invitation_id=invitation_id,
            new_status=new_status,
        )
