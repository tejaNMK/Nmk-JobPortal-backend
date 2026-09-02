from fastapi import HTTPException

from app.repository.super_admin.employer_repo import EmployerRepository
from app.schema.super_admin.employer import (
    EmployerDetails,
    EmployerItem,
    EmployerListResponse,
    EmployerStatusRequest,
    EmployerUpdateRequest,
    EmployerVerificationRequest,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService


class EmployerService:

    @staticmethod
    def _verification_status(email_verified: bool, mobile_verified: bool) -> str:
        if email_verified and mobile_verified:
            return "VERIFIED"
        if email_verified or mobile_verified:
            return "PARTIALLY_VERIFIED"
        return "NOT_VERIFIED"

    @staticmethod
    async def list_employers(
        session,
        page,
        page_size,
        search,
        sort_by="created_at",
        sort_order="desc",
    ):

        employers, total = await EmployerRepository.list_employers(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        items = []

        for user, employer, subscription_name in employers:

            role_codes = {
                role.role_code
                for role in user.roles
            }
            email_verified = bool(user.email_verified)
            mobile_verified = bool(user.mobile_verified)

            items.append(
                EmployerItem(
                    user_id=user.user_id,
                    employer_id=employer.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    mobile_number=user.mobile_number,
                    company_name=employer.company_name,
                    created_at=user.created_at,
                    registered_date=employer.created_at,
                    last_login=user.last_login_at,
                    subscription=subscription_name,
                    email_verified=email_verified,
                    mobile_verified=mobile_verified,
                    verification_status=EmployerService._verification_status(
                        email_verified=email_verified,
                        mobile_verified=mobile_verified,
                    ),
                    company_verification_status=employer.verification_status,
                    status=employer.status,
                    is_admin="ROLE_ADMIN" in role_codes,
                )
            )

        return EmployerListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def make_admin(
        session,
        user_id,
        actor=None,
    ):

        user = await EmployerRepository.get_user(
            session=session,
            user_id=user_id,
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Employer not found.",
            )

        role_codes = {
            role.role_code
            for role in user.roles
        }

        if "ROLE_RECRUITER" not in role_codes:
            raise HTTPException(
                status_code=400,
                detail="User is not an employer.",
            )

        if "ROLE_ADMIN" in role_codes:
            raise HTTPException(
                status_code=400,
                detail="Employer is already an Admin.",
            )

        admin_role = await EmployerRepository.get_role(
            session=session,
            role_code="ROLE_ADMIN",
        )

        if not admin_role:
            raise HTTPException(
                status_code=404,
                detail="ROLE_ADMIN not found.",
            )

        await EmployerRepository.assign_role(
            session=session,
            user_id=user.user_id,
            role_id=admin_role.role_id,
        )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="ADMIN_CREATED",
                entity_type="Admin",
                entity_id=str(user.user_id),
                target_entity_name=(
                    f"{user.first_name or ''} {user.last_name or ''}"
                ).strip() or user.email,
                description="Employer promoted to Admin",
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="ADMIN_CREATED",
            title="Admin created",
            message="Employer was promoted to Admin.",
            entity_type="user",
            entity_id=str(user.user_id),
            target_route=f"/super-admin/employers/{user.user_id}",
            event_key=f"admin_created:{user.user_id}",
            commit=True,
        )

        return {
            "message": "Employer promoted to Admin successfully."
        }
    
    @staticmethod
    async def remove_admin(
        session,
        user_id,
        actor=None,
    ):

        user = await EmployerRepository.get_user(
            session=session,
            user_id=user_id,
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Employer not found.",
            )

        role_codes = {
            role.role_code
            for role in user.roles
        }

        if "ROLE_ADMIN" not in role_codes:
            raise HTTPException(
                status_code=400,
                detail="Employer is not an Admin.",
            )

        admin_role = await EmployerRepository.get_role(
            session=session,
            role_code="ROLE_ADMIN",
        )

        if not admin_role:
            raise HTTPException(
                status_code=404,
                detail="ROLE_ADMIN not found.",
            )

        user_role = await EmployerRepository.get_user_role(
            session=session,
            user_id=user.user_id,
            role_id=admin_role.role_id,
        )

        if user_role:
            await EmployerRepository.remove_role(
                session=session,
                user_role=user_role,
            )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="ADMIN_DELETED",
                entity_type="Admin",
                entity_id=str(user.user_id),
                target_entity_name=(
                    f"{user.first_name or ''} {user.last_name or ''}"
                ).strip() or user.email,
                description="Admin access removed",
            )

        return {
            "message": "Admin access removed successfully."
        }

    @staticmethod
    async def get_employer(
        session,
        employer_id,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Employer not found.")

        user, employer = row
        email_verified = bool(user.email_verified)
        mobile_verified = bool(user.mobile_verified)
        job_counts = await EmployerRepository.get_job_counts(
            session=session,
            employer_id=employer.id,
        )
        subscription = await EmployerRepository.get_active_subscription(
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

        recruiter_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        )

        return EmployerDetails(
            user_id=user.user_id,
            employer_id=employer.id,
            company_name=employer.company_name,
            company_logo=employer.company_logo_url,
            company_description=employer.company_description,
            industry=employer.industry,
            website=employer.website_url or employer.company_website,
            recruiter_name=recruiter_name,
            email=user.email,
            phone=user.mobile_number,
            email_verified=email_verified,
            mobile_verified=mobile_verified,
            verification_status=EmployerService._verification_status(
                email_verified=email_verified,
                mobile_verified=mobile_verified,
            ),
            company_verification_status=employer.verification_status,
            rejection_reason=employer.rejection_reason,
            status=employer.status,
            suspension_reason=employer.suspension_reason,
            subscription=subscription_payload,
            total_jobs=job_counts["total_jobs"],
            active_jobs=job_counts["active_jobs"],
            closed_jobs=job_counts["closed_jobs"],
            registered_date=employer.created_at,
            last_login=user.last_login_at,
        )

    @staticmethod
    async def update_employer(
        session,
        employer_id,
        request: EmployerUpdateRequest,
        actor=None,
    ):
        data = request.model_dump(exclude_unset=True)
        user_fields = {"first_name", "last_name", "mobile_number"}
        employer_fields = {
            "company_name",
            "company_email",
            "company_mobile",
            "company_website",
            "company_description",
            "industry",
            "company_location",
            "website_url",
            "linkedin_url",
            "job_title",
            "department",
            "bio",
        }
        result = await EmployerRepository.update_employer(
            session=session,
            employer_id=employer_id,
            user_updates={key: data[key] for key in user_fields if key in data},
            employer_updates={key: data[key] for key in employer_fields if key in data},
        )
        if not result:
            raise HTTPException(status_code=404, detail="Employer not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="UPDATE_EMPLOYER",
                entity_type="Employer",
                entity_id=employer_id,
                description="Updated employer profile",
            )

        return {"message": "Employer updated successfully."}

    @staticmethod
    async def update_employer_status(
        session,
        employer_id,
        request: EmployerStatusRequest,
        actor=None,
    ):
        status = request.status.upper()
        if status not in {"ACTIVE", "INACTIVE", "SUSPENDED"}:
            raise HTTPException(
                status_code=400,
                detail="Status must be ACTIVE, INACTIVE, or SUSPENDED.",
            )
        if status == "SUSPENDED" and not request.reason:
            raise HTTPException(status_code=400, detail="Suspension reason is required.")

        result = await EmployerRepository.update_status(
            session=session,
            employer_id=employer_id,
            status=status,
            reason=request.reason,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Employer not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="EMPLOYER_SUSPENDED" if status == "SUSPENDED" else "UPDATE_EMPLOYER",
                entity_type="Employer",
                entity_id=employer_id,
                description=f"Changed employer status to {status}",
            )
        if status in {"ACTIVE", "INACTIVE"}:
            await NotificationService.create_for_super_admins(
                session,
                notification_type="USER_ACTIVATED" if status == "ACTIVE" else "USER_DEACTIVATED",
                title="User status changed",
                message=f"Employer status changed to {status}.",
                entity_type="user",
                entity_id=str(employer_id),
                target_route=f"/super-admin/employers/{employer_id}",
                metadata={"status": status},
                event_key=f"user_status:employer:{employer_id}:{status}",
                commit=True,
            )

        return {"message": "Employer status updated successfully."}

    @staticmethod
    async def verify_employer(
        session,
        employer_id,
        request: EmployerVerificationRequest,
        actor=None,
    ):
        status = request.status.upper()
        status_aliases = {
            "APPROVE": "APPROVED",
            "APPROVED": "APPROVED",
            "REJECT": "REJECTED",
            "REJECTED": "REJECTED",
        }
        verification_status = status_aliases.get(status)
        if not verification_status:
            raise HTTPException(
                status_code=400,
                detail="Verification status must be APPROVED or REJECTED.",
            )
        if verification_status == "REJECTED" and not request.reason:
            raise HTTPException(status_code=400, detail="Rejection reason is required.")

        result = await EmployerRepository.update_verification(
            session=session,
            employer_id=employer_id,
            verification_status=verification_status,
            reason=request.reason,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Employer not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="APPROVE_COMPANY" if verification_status == "APPROVED" else "REJECT_COMPANY",
                entity_type="Employer",
                entity_id=employer_id,
                description=f"Employer verification {verification_status.lower()}",
            )

        return {"message": "Employer verification updated successfully."}

    @staticmethod
    async def approve_employer_company(
        session,
        employer_id,
        actor=None,
    ):
        row = await EmployerRepository.get_employer(
            session=session,
            employer_id=employer_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Employer not found.")

        _user, employer = row
        if employer.verification_status == "APPROVED" or employer.is_verified == 1:
            raise HTTPException(status_code=400, detail="Company is already approved.")

        result = await EmployerRepository.approve_employer_company(
            session=session,
            employer_id=employer_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Employer not found.")

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="APPROVE_COMPANY",
                entity_type="Employer",
                entity_id=employer_id,
                description="Approved employer company",
            )

        return await EmployerService.get_employer(
            session=session,
            employer_id=employer_id,
        )

    @staticmethod
    async def delete_employer(
        session,
        user_id,
        actor=None,
    ):
        result = await EmployerRepository.soft_delete_employer_by_user_id(
            session=session,
            user_id=user_id,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Employer not found.")

        user, employer = result
        target_name = (
            getattr(employer, "company_name", None)
            or " ".join(
                part
                for part in [
                    getattr(user, "first_name", None),
                    getattr(user, "last_name", None),
                ]
                if part
            )
            or getattr(user, "email", None)
        )

        if actor:
            await ActivityLogService.create_log(
                session=session,
                actor=actor,
                action="EMPLOYER_DELETED",
                entity_type="Employer",
                entity_id=str(user.user_id),
                target_entity_name=target_name,
                description="Deleted employer account",
                metadata={
                    "user_id": str(user.user_id),
                    "employer_profile_id": employer.id,
                    "deletion_type": "soft",
                },
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="USER_DELETED",
            title="User deleted",
            message="Employer account deleted.",
            entity_type="user",
            entity_id=str(user.user_id),
            target_route="/super-admin/employers",
            event_key=f"user_deleted:employer:{user.user_id}",
            commit=True,
        )

        return {
            "user_id": str(user.user_id),
            "employer_profile_id": employer.id,
            "deletion_type": "soft",
        }
