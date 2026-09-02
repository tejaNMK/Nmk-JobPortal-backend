from fastapi import HTTPException

from app.repository.super_admin.candidate_repo import CandidateRepository
from app.schema.super_admin.candidate import (
    CandidateUpdateRequest,
    CandidateItem,
    CandidateListResponse,
    CandidateDetails,
    CandidateStatusRequest,
    CandidateStatistics,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService


class CandidateService:

    @staticmethod
    async def list_candidates(
        session,
        page,
        page_size,
        search,
        status=None,
        subscription=None,
        registered_from=None,
        registered_to=None,
        sort_by="created_at",
        sort_order="desc",
    ):

        candidates, total = await CandidateRepository.list_candidates(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            subscription=subscription,
            registered_from=registered_from,
            registered_to=registered_to,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        items = []

        for profile, user, subscription_name, resume_count in candidates:
            full_name = " ".join(
                part for part in [user.first_name, user.last_name] if part
            )

            items.append(
                CandidateItem(
                    user_id=user.user_id,
                    candidate_id=profile.candidate_id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    full_name=full_name,
                    email=user.email,
                    mobile_number=user.mobile_number,
                    phone=user.mobile_number,
                    headline=profile.headline,
                    total_experience=profile.total_experience,
                    current_location=profile.current_location,
                    profile_completion_pct=profile.profile_completion_pct,
                    resume_uploaded=(resume_count or 0) > 0,
                    subscription=subscription_name,
                    created_at=user.created_at,
                    registered_on=user.created_at,
                    last_login=user.last_login_at,
                    open_to_work=profile.open_to_work,
                    status=profile.status,
                )
            )

        return CandidateListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def get_candidate(
        session,
        candidate_id,
    ):

        result = await CandidateRepository.get_candidate(
            session=session,
            candidate_id=candidate_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found.",
            )

        profile, user = result

        statistics = await CandidateRepository.get_candidate_statistics(
            session=session,
            candidate_id=candidate_id,
        )
        resume_detail = await CandidateRepository.get_latest_resume_detail(
            session=session,
            candidate_id=candidate_id,
        )
        resumes = await CandidateRepository.list_resumes(
            session=session,
            candidate_id=candidate_id,
        )
        subscription = await CandidateRepository.get_active_subscription(
            session=session,
            user_id=user.user_id,
        )
        subscription_payload = None
        if subscription:
            user_subscription, plan = subscription
            subscription_payload = {
                "user_subscription_id": str(user_subscription.user_subscription_id),
                "subscription_id": str(plan.subscription_id),
                "subscription_name": plan.subscription_name,
                "status": user_subscription.status,
                "start_date": user_subscription.start_date,
                "end_date": user_subscription.end_date,
            }
        full_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        )

        return CandidateDetails(
            user_id=user.user_id,
            candidate_id=profile.candidate_id,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=full_name,
            email=user.email,
            mobile_number=user.mobile_number,
            headline=profile.headline,
            summary=profile.summary,
            total_experience=profile.total_experience,
            current_location=profile.current_location,
            preferred_location=profile.preferred_location,
            profile_completion_pct=profile.profile_completion_pct,
            open_to_work=profile.open_to_work,
            status=profile.status,
            suspension_reason=profile.suspension_reason,
            subscription=subscription_payload,
            verification_status={
                "email_verified": user.email_verified,
                "mobile_verified": user.mobile_verified,
            },
            resume_information=[
                {
                    "resume_id": resume.resume_id,
                    "file_name": resume.file_name,
                    "version_no": resume.version_no,
                    "uploaded_at": resume.uploaded_at,
                    "is_active": resume.is_active,
                    "file_size": resume.file_size,
                }
                for resume in resumes
            ],
            skills=resume_detail.skills_json if resume_detail else profile.skills_summary,
            experience=resume_detail.experience_json if resume_detail else None,
            education=resume_detail.education_json if resume_detail else None,
            last_login=user.last_login_at,
            statistics=CandidateStatistics(
                applications=statistics["applications"],
                saved_jobs=statistics["saved_jobs"],
                job_alerts=statistics["job_alerts"],
                resumes=statistics["resumes"],
            ),
        )
    
    @staticmethod
    async def activate_candidate(
        session,
        candidate_id,
        actor=None,
    ):

        result = await CandidateRepository.get_candidate(
            session=session,
            candidate_id=candidate_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found.",
            )

        profile, user = result

        await CandidateRepository.update_candidate_status(
            session=session,
            candidate_id=candidate_id,
            status="ACTIVE",
            reason=None,
        )

        await CandidateRepository.update_user_status(
            session=session,
            user_id=user.user_id,
            status="ACTIVE",
        )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="UPDATE_CANDIDATE",
                entity_type="Candidate",
                entity_id=candidate_id,
                description="Activated candidate account",
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="USER_ACTIVATED",
            title="User activated",
            message="Candidate account activated.",
            entity_type="user",
            entity_id=str(user.user_id),
            target_route=f"/super-admin/candidates/{candidate_id}",
            event_key=f"user_activated:{user.user_id}",
            commit=True,
        )

        return {
            "message": "Candidate activated successfully."
        }


    @staticmethod
    async def deactivate_candidate(
        session,
        candidate_id,
        actor=None,
    ):

        result = await CandidateRepository.get_candidate(
            session=session,
            candidate_id=candidate_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found.",
            )

        profile, user = result

        await CandidateRepository.update_candidate_status(
            session=session,
            candidate_id=candidate_id,
            status="INACTIVE",
            reason=None,
        )

        await CandidateRepository.update_user_status(
            session=session,
            user_id=user.user_id,
            status="INACTIVE",
        )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="DISABLE_USER",
                entity_type="Candidate",
                entity_id=candidate_id,
                description="Deactivated candidate account",
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="USER_DEACTIVATED",
            title="User deactivated",
            message="Candidate account deactivated.",
            entity_type="user",
            entity_id=str(user.user_id),
            target_route=f"/super-admin/candidates/{candidate_id}",
            event_key=f"user_deactivated:{user.user_id}",
            commit=True,
        )

        return {
            "message": "Candidate deactivated successfully."
        }

    @staticmethod
    async def update_candidate(
        session,
        candidate_id,
        request: CandidateUpdateRequest,
        actor=None,
    ):
        data = request.model_dump(exclude_unset=True)
        user_fields = {"first_name", "last_name", "mobile_number"}
        profile_fields = {
            "headline",
            "summary",
            "current_location",
            "preferred_location",
            "skills_summary",
            "profile_visibility",
            "searchable_flag",
            "open_to_work",
        }
        user_updates = {key: data[key] for key in user_fields if key in data}
        profile_updates = {key: data[key] for key in profile_fields if key in data}

        result = await CandidateRepository.update_candidate(
            session=session,
            candidate_id=candidate_id,
            user_updates=user_updates,
            profile_updates=profile_updates,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="UPDATE_CANDIDATE",
                entity_type="Candidate",
                entity_id=candidate_id,
                description="Updated candidate profile",
            )

        return {"message": "Candidate updated successfully."}

    @staticmethod
    async def update_candidate_status(
        session,
        candidate_id,
        request: CandidateStatusRequest,
        actor=None,
    ):
        status = request.status.upper()
        if status not in {"ACTIVE", "INACTIVE", "SUSPENDED"}:
            raise HTTPException(
                status_code=400,
                detail="Status must be ACTIVE, INACTIVE, or SUSPENDED.",
            )
        if status == "SUSPENDED" and not request.reason:
            raise HTTPException(
                status_code=400,
                detail="Suspension reason is required.",
            )

        result = await CandidateRepository.get_candidate(
            session=session,
            candidate_id=candidate_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Candidate not found.")
        profile, user = result

        await CandidateRepository.update_candidate_status(
            session=session,
            candidate_id=candidate_id,
            status=status,
            reason=request.reason,
        )
        await CandidateRepository.update_user_status(
            session=session,
            user_id=user.user_id,
            status="SUSPENDED" if status == "SUSPENDED" else status,
        )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="CANDIDATE_SUSPENDED" if status == "SUSPENDED" else "UPDATE_CANDIDATE",
                entity_type="Candidate",
                entity_id=profile.candidate_id,
                description=f"Changed candidate status to {status}",
            )
        if status in {"ACTIVE", "INACTIVE"}:
            await NotificationService.create_for_super_admins(
                session,
                notification_type="USER_ACTIVATED" if status == "ACTIVE" else "USER_DEACTIVATED",
                title="User status changed",
                message=f"Candidate status changed to {status}.",
                entity_type="user",
                entity_id=str(user.user_id),
                target_route=f"/super-admin/candidates/{candidate_id}",
                metadata={"status": status},
                event_key=f"user_status:{user.user_id}:{status}",
                commit=True,
            )

        return {"message": "Candidate status updated successfully."}

    @staticmethod
    async def delete_candidate(
        session,
        candidate_id,
        actor=None,
    ):
        deleted_by = None
        if isinstance(actor, dict):
            deleted_by = actor.get("user_id")

        result = await CandidateRepository.soft_delete_candidate(
            session=session,
            candidate_id=candidate_id,
            deleted_by=deleted_by,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Candidate not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="DELETE_USER",
                entity_type="Candidate",
                entity_id=candidate_id,
                description="Deleted candidate account",
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="USER_DELETED",
            title="User deleted",
            message="Candidate account deleted.",
            entity_type="user",
            entity_id=str(candidate_id),
            target_route="/super-admin/candidates",
            event_key=f"user_deleted:candidate:{candidate_id}",
            commit=True,
        )

        return {"message": "Candidate deleted successfully."}
