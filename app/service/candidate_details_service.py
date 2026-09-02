from fastapi import HTTPException

from app.repository.candidate_repository.candidate_details_repo import (
    CandidateDetailsRepo,
)
from app.service.subscription.subscription_validator import SubscriptionValidator


class CandidateDetailsService:

    @staticmethod
    async def get_candidate_details(
        session,
        candidate_id: str,
        user_id=None,
    ):

        if not candidate_id:
            raise HTTPException(
                status_code=400,
                detail="Candidate ID is required",
            )

        if user_id:
            validator = SubscriptionValidator(
                session=session,
                user_id=user_id,
                role="EMPLOYER",
            )
            await validator.require_feature("candidate_search")

        record = (
            await CandidateDetailsRepo.get_candidate_details(
                session=session,
                candidate_id=candidate_id,
            )
        )

        if not record:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found",
            )

        profile, user = record

        latest_resume = (
            max(
                profile.resumes,
                key=lambda x: x.uploaded_at,
            )
            if profile.resumes
            else None
        )

        latest_resume_detail = (
            max(
                profile.resume_details,
                key=lambda x: x.generated_at,
            )
            if profile.resume_details
            else None
        )

        applications = []
        timeline = []
        notes = []

        for application in profile.applications:

            applications.append(
                {
                    "application_id":
                        application.application_id,
                    "job_id":
                        application.job_id,
                    "job_title":
                        application.job.title
                        if application.job
                        else None,
                    "application_status":
                        application.application_status,
                    "applied_at":
                        application.applied_at,
                }
            )

            for status_history in (
                application.status_history
            ):
                timeline.append(
                    {
                        "type":
                            "STATUS_CHANGE",
                        "old_status":
                            status_history.old_status,
                        "new_status":
                            status_history.new_status,
                        "changed_at":
                            status_history.changed_at,
                    }
                )

            for interview in (
                application.interviews
            ):
                timeline.append(
                    {
                        "type":
                            "INTERVIEW",
                        "scheduled_at":
                            interview.scheduled_at,
                        "mode":
                            interview.mode,
                        "status":
                            interview.status,
                    }
                )

            for note in application.notes:
                notes.append(
                    {
                        "note_id":
                            note.note_id,
                        "note_text":
                            note.note_text,
                        "created_at":
                            note.created_at,
                    }
                )

        return {
            "candidate_id":
                profile.candidate_id,

            "full_name":
                (
                    f"{user.first_name} "
                    f"{user.last_name or ''}"
                ).strip(),

            "email":
                user.email,

            "phone_number":
                user.mobile_number,

            "location":
                profile.current_location,

            "headline":
                profile.headline,

            "summary":
                profile.summary,

            "total_experience":
                profile.total_experience,

            "skills":
                (
                    latest_resume_detail.skills_json
                    if latest_resume_detail
                    else None
                ),

            "experience":
                (
                    latest_resume_detail.experience_json
                    if latest_resume_detail
                    else None
                ),

            "education":
                (
                    latest_resume_detail.education_json
                    if latest_resume_detail
                    else None
                ),

            "resume":
                {
                    "resume_id":
                        latest_resume.resume_id,
                    "file_name":
                        latest_resume.file_name,
                    "file_path":
                        latest_resume.file_path,
                }
                if latest_resume
                else None,

            "applications":
                applications,

            "timeline":
                timeline,

            "notes":
                notes,
        }
