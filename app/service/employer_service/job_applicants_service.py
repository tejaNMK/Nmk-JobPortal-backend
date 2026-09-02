import logging
from datetime import timezone
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import APPLICANT_RANKING_MAX_CANDIDATES_PER_REQUEST
from app.service import s3_service
from app.utils.image_urls import resolve_profile_image_url
from app.repository.employer_repository.job_applicants_repo import (
    JobApplicantsRepo,
)
from app.schema.job_applicants import (
    ApplicantFilterParams,
    ApplicantListItem,
    ApplicantListResponse,
    ApplicantProfileResponse,
    EmployerApplicationStatusUpdateRequest,
    EmployerApplicationStatusUpdateResponse,
    ResumeDownloadResponse,
)

logger = logging.getLogger(__name__)
from app.service.employer_service.applicant_ranking_service import (
    ApplicantRankingResult,
    ApplicantRankingService,
)
from app.service.subscription.subscription_validator import SubscriptionValidator


PREVIEWABLE_RESUME_TYPES = {
    "application/pdf",
}


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


def _display_image_url(stored_value: str | None) -> str | None:
    return resolve_profile_image_url(stored_value)


def _application_urls(application_id: str, has_resume: bool) -> dict[str, str | None]:
    base = f"/employer/job-applicants/{application_id}"
    return {
        "view_profile_url": base,
        "view_resume_url": f"{base}/resume/preview-file" if has_resume else None,
        "download_resume_url": f"{base}/resume/download-file" if has_resume else None,
    }


def _resume_content_type(resume) -> str | None:
    if not resume:
        return None
    name = (getattr(resume, "file_name", None) or "").lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".doc"):
        return "application/msword"
    if name.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None


def _utc_timestamp(value) -> str:
    if not value:
        return ""
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


_EMPLOYER_STATUS_TRANSITIONS = {
    "APPLIED": {"APPLIED", "REVIEW", "SHORTLISTED", "REJECTED", "ARCHIVED"},
    "REVIEW": {"REVIEW", "SHORTLISTED", "REJECTED", "INTERVIEW", "ARCHIVED"},
    "SHORTLISTED": {
        "SHORTLISTED",
        "REJECTED",
        "INTERVIEW",
        "INTERVIEW_SCHEDULED",
        "ON_HOLD",
        "HIRED",
    },
    "REJECTED": {"REJECTED", "SHORTLISTED"},
    "ON_HOLD": {"ON_HOLD", "SHORTLISTED", "REJECTED", "INTERVIEW_SCHEDULED"},
    "INTERVIEW": {"INTERVIEW", "OFFER", "REJECTED", "HIRED", "ARCHIVED"},
    "INTERVIEW_SCHEDULED": {
        "INTERVIEW_SCHEDULED",
        "OFFER",
        "REJECTED",
        "HIRED",
        "ON_HOLD",
    },
    "OFFER": {"OFFER", "HIRED", "REJECTED", "ARCHIVED"},
    "HIRED": {"HIRED", "SHORTLISTED", "REJECTED", "ARCHIVED"},
    "ARCHIVED": {"ARCHIVED"},
}


def _application_resume(app, resume):
    if resume:
        return resume
    if not (
        getattr(app, "resume_blob_ref_snapshot", None)
        or getattr(app, "resume_file_path_snapshot", None)
        or getattr(app, "resume_file_name_snapshot", None)
    ):
        return None
    return SimpleNamespace(
        resume_id=getattr(app, "resume_id", None),
        file_name=getattr(app, "resume_file_name_snapshot", None),
        file_path=getattr(app, "resume_file_path_snapshot", None),
        blob_ref=getattr(app, "resume_blob_ref_snapshot", None),
        file_size=getattr(app, "resume_file_size_snapshot", None),
    )


def _unpack_applicant_row(row):
    if len(row) == 5:
        app, profile, user, resume, job = row
        return app, profile, user, resume, job, None
    return row


class JobApplicantsService:

    @staticmethod
    async def list_applicants(
        session: AsyncSession,
        user_id: UUID,
        filters: ApplicantFilterParams,
    ) -> ApplicantListResponse:

        employer_id = await JobApplicantsRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        ai_rank_enabled = bool(filters.ai_rank)
        if ai_rank_enabled:
            await SubscriptionValidator(
                session=session,
                user_id=user_id,
                role="EMPLOYER",
            ).require_feature("ai_applicant_ranking")
            max_ranked_candidates = max(1, APPLICANT_RANKING_MAX_CANDIDATES_PER_REQUEST)
            if (filters.page - 1) * filters.page_size >= max_ranked_candidates:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "AI ranking is limited to the first "
                        f"{max_ranked_candidates} applicants per request."
                    ),
                )
        else:
            max_ranked_candidates = None

        total, rows = await JobApplicantsRepo.get_job_applicants(
            session=session,
            employer_id=employer_id,
            job_id=filters.job_id,
            search=filters.search,
            status=filters.status,
            sort_by="best_match" if ai_rank_enabled else filters.sort_by,
            sort_order=filters.sort_order,
            page=filters.page,
            page_size=filters.page_size,
            ranking_limit=(
                min(
                    filters.page * filters.page_size,
                    max_ranked_candidates,
                )
                if ai_rank_enabled
                else None
            ),
        )

        items = []

        for row in rows:
            app, profile, user, resume, job, resume_detail = _unpack_applicant_row(row)
            resume = _application_resume(app, resume)
            has_resume = resume is not None
            urls = _application_urls(app.application_id, has_resume)
            ranking = await JobApplicantsService._rank_if_needed(
                session=session,
                employer_id=employer_id,
                enabled=ai_rank_enabled,
                app=app,
                profile=profile,
                job=job,
                resume_detail=resume_detail,
            )

            items.append(
                ApplicantListItem(
                    application_id=app.application_id,
                    candidate_id=profile.candidate_id,
                    applicant_name=_full_name(user),
                    email=user.email,
                    phone_number=user.mobile_number,
                    profile_image_url=_display_image_url(
                        getattr(user, "profile_image_url", None)
                    ),
                    current_designation=getattr(profile, "headline", None),
                    total_experience=float(getattr(profile, "total_experience", 0))
                    if getattr(profile, "total_experience", None)
                    else None,
                    applied_position=job.title,
                    job_id=getattr(job, "job_id", ""),
                    resume_name=resume.file_name if resume else None,
                    has_resume=has_resume,
                    **urls,
                    referral_contact=app.referral_contact,
                    source=app.source,
                    application_date=app.applied_at,
                    application_status=app.application_status,
                    match_score=ranking.match_score if ranking else None,
                    match_label=ranking.match_label if ranking else None,
                    match_reasons=ranking.match_reasons if ranking else [],
                    missing_requirements=ranking.missing_requirements if ranking else [],
                )
            )

        if ai_rank_enabled:
            reverse = filters.sort_order.lower() != "asc"
            items.sort(
                key=lambda item: (
                    item.match_score if item.match_score is not None else -1,
                    item.application_date,
                ),
                reverse=reverse,
            )
            start = (filters.page - 1) * filters.page_size
            end = start + filters.page_size
            items = items[start:end]

        return ApplicantListResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            items=items,
        )

    @staticmethod
    async def get_applicant_profile(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ) -> ApplicantProfileResponse:

        employer_id = await JobApplicantsRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        row = await JobApplicantsRepo.get_application_details(
            session,
            employer_id,
            application_id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Applicant not found"
            )

        app, profile, user, resume, job, resume_detail = _unpack_applicant_row(row)
        resume = _application_resume(app, resume)
        has_resume = resume is not None
        urls = _application_urls(app.application_id, has_resume)
        ranking = await JobApplicantsService._rank_if_needed(
            session=session,
            employer_id=employer_id,
            enabled=False,
            app=app,
            profile=profile,
            job=job,
            resume_detail=resume_detail,
        )

        return ApplicantProfileResponse(
            application_id=app.application_id,
            candidate_id=profile.candidate_id,
            applicant_name=_full_name(user),
            email=user.email,
            phone_number=user.mobile_number,
            headline=getattr(profile, "headline", None),
            summary=getattr(profile, "summary", None),
            total_experience=float(profile.total_experience)
            if getattr(profile, "total_experience", None)
            else None,
            current_location=getattr(profile, "current_location", None),
            preferred_location=getattr(profile, "preferred_location", None),
            skills_summary=getattr(profile, "skills_summary", None),
            profile_image_url=_display_image_url(
                getattr(user, "profile_image_url", None)
            ),
            current_designation=getattr(profile, "headline", None),
            job_id=getattr(job, "job_id", ""),
            applied_position=job.title,
            referral_contact=app.referral_contact,
            source=app.source,
            application_status=app.application_status,
            application_date=app.applied_at,
            resume_name=resume.file_name if resume else None,
            has_resume=has_resume,
            **urls,
            match_score=ranking.match_score if ranking else None,
            match_label=ranking.match_label if ranking else None,
            match_reasons=ranking.match_reasons if ranking else [],
            missing_requirements=ranking.missing_requirements if ranking else [],
        )

    @staticmethod
    async def _get_application_resume_row(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ):

        employer_id = await JobApplicantsRepo.get_employer_id(
            session,
            user_id
        )
        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        row = await JobApplicantsRepo.get_application_details(
            session,
            employer_id,
            application_id,
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Resume not found"
            )

        app, profile, user, resume, job, _resume_detail = _unpack_applicant_row(row)
        resume = _application_resume(app, resume)

        if not resume:
            raise HTTPException(
                status_code=404,
                detail="Resume not found"
            )

        return app, profile, user, resume, job

    @staticmethod
    async def _rank_if_needed(
        *,
        session: AsyncSession,
        employer_id: str,
        enabled: bool,
        app,
        profile,
        job,
        resume_detail,
    ) -> ApplicantRankingResult | None:
        if not enabled:
            return None
        return await ApplicantRankingService.rank_applicant(
            session=session,
            employer_id=employer_id,
            application=app,
            profile=profile,
            job=job,
            resume_detail=resume_detail,
        )

    @staticmethod
    async def get_resume(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
    ) -> ResumeDownloadResponse:

        app, profile, user, resume, job = await JobApplicantsService._get_application_resume_row(
            session=session,
            user_id=user_id,
            application_id=application_id,
        )

        return ResumeDownloadResponse(
            resume_id=resume.resume_id,
            file_name=resume.file_name,
            file_path=None,
            file_size=getattr(resume, "file_size", None),
            content_type=_resume_content_type(resume),
            is_previewable=_resume_content_type(resume) in PREVIEWABLE_RESUME_TYPES,
            url=f"/employer/job-applicants/{app.application_id}/resume/download-file",
            preview_url=f"/employer/job-applicants/{app.application_id}/resume/preview-file",
            download_url=f"/employer/job-applicants/{app.application_id}/resume/download-file",
        )

    @staticmethod
    async def get_resume_file(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
        count_as_download: bool = True,
    ) -> tuple[bytes, str, str | None]:
        app, profile, user, resume, job = await JobApplicantsService._get_application_resume_row(
            session=session,
            user_id=user_id,
            application_id=application_id,
        )

        if not resume.blob_ref:
            raise HTTPException(status_code=404, detail="Resume file not found")

        content, content_type = s3_service.fetch_object_bytes(resume.blob_ref)
        return content, (resume.file_name or "resume"), content_type

    @staticmethod
    async def update_application_status(
        session: AsyncSession,
        user_id: UUID,
        application_id: str,
        payload: EmployerApplicationStatusUpdateRequest,
    ) -> EmployerApplicationStatusUpdateResponse:

        employer_id = await JobApplicantsRepo.get_employer_id(
            session,
            user_id
        )

        if not employer_id:
            raise HTTPException(
                status_code=403,
                detail="Recruiter profile not found"
            )

        application = await JobApplicantsRepo.get_employer_application(
            session=session,
            employer_id=employer_id,
            application_id=application_id,
        )

        if not application:
            existing_application = await JobApplicantsRepo.get_application_by_id(
                session=session,
                application_id=application_id,
            )
            if not existing_application:
                raise HTTPException(
                    status_code=404,
                    detail="Application not found"
                )
            raise HTTPException(
                status_code=403,
                detail="Application does not belong to this employer"
            )

        previous_status = (application.application_status or "").upper()
        new_status = payload.status.upper()
        allowed_statuses = _EMPLOYER_STATUS_TRANSITIONS.get(
            previous_status,
            {previous_status},
        )

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status transition from {previous_status} "
                    f"to {new_status}"
                ),
            )

        if new_status == previous_status:
            return EmployerApplicationStatusUpdateResponse(
                application_id=application.application_id,
                job_id=getattr(application, "job_id", ""),
                candidate_id=getattr(application, "candidate_id", ""),
                previous_status=previous_status,
                application_status=application.application_status,
                updated_at=_utc_timestamp(application.updated_at),
            )

        updated = await JobApplicantsRepo.update_application_status(
            session=session,
            application=application,
            status=new_status,
            changed_by=user_id,
            reason=payload.reason,
        )

        return EmployerApplicationStatusUpdateResponse(
            application_id=updated.application_id,
            job_id=getattr(updated, "job_id", getattr(application, "job_id", "")),
            candidate_id=getattr(
                updated,
                "candidate_id",
                getattr(application, "candidate_id", ""),
            ),
            previous_status=previous_status,
            application_status=updated.application_status,
            updated_at=_utc_timestamp(updated.updated_at),
        )
