import csv
from io import BytesIO, StringIO
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job
from app.repository.super_admin.dashboard_api_repo import (
    SuperAdminDashboardRepository,
)
from app.schema.super_admin.dashboard_api import (
    JobOverviewResponse,
    RecentRegistrationItem,
    RecentRegistrationListResponse,
    SuperAdminJobBulkActionResponse,
    SuperAdminJobItem,
    SuperAdminJobListResponse,
    SuperAdminUserItem,
    SuperAdminUserListResponse,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService
from app.service.subscription.subscription_validator import SubscriptionValidator
from app.utils.date_range import NormalizedDateRange


class SuperAdminDashboardService:
    @staticmethod
    async def _ensure_bulk_activate_within_plan_limits(
        session: AsyncSession,
        job_ids: list[str],
    ) -> None:
        rows = await session.execute(
            select(
                Job.employer_id,
                EmployerProfile.user_id,
                func.count(Job.job_id).label("jobs_to_publish"),
            )
            .join(EmployerProfile, EmployerProfile.id == Job.employer_id)
            .where(
                Job.job_id.in_(job_ids),
                Job.is_deleted.is_(False),
                Job.status != "PUBLISHED",
            )
            .group_by(Job.employer_id, EmployerProfile.user_id)
        )

        for employer_id, user_id, jobs_to_publish in rows.all():
            validator = SubscriptionValidator(
                session=session,
                user_id=user_id,
                role="EMPLOYER",
            )
            limit = await validator.get_limit("max_published_jobs")
            if limit is None:
                continue

            current_count_result = await session.execute(
                select(func.count(Job.job_id)).where(
                    Job.employer_id == employer_id,
                    Job.status == "PUBLISHED",
                    Job.is_deleted.is_(False),
                )
            )
            current_count = int(current_count_result.scalar_one() or 0)
            if current_count + int(jobs_to_publish or 0) > limit:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Bulk activate would exceed max_published_jobs for employer {employer_id}. "
                        f"Current plan allows {limit} published jobs."
                    ),
                )

    @staticmethod
    def _range_value(min_value, max_value) -> Optional[str]:
        if min_value is None and max_value is None:
            return None
        if min_value is None:
            return str(max_value)
        if max_value is None:
            return str(min_value)
        if min_value == max_value:
            return str(min_value)
        return f"{min_value}-{max_value}"

    @staticmethod
    def _job_item(row) -> SuperAdminJobItem:
        job, employer, user = row
        recruiter_name = None
        if user:
            recruiter_name = " ".join(
                part for part in [user.first_name, user.last_name] if part
            ) or user.email
        industry = getattr(employer, "industry", None) if employer else None
        company_name = job.company_name or (
            getattr(employer, "company_name", None) if employer else None
        )
        salary_range = SuperAdminDashboardService._range_value(
            job.salary_min,
            job.salary_max,
        )

        return SuperAdminJobItem(
            job_id=job.job_id,
            job_title=job.title,
            company_name=company_name,
            recruiter_name=recruiter_name,
            location=job.location,
            employment_type=job.employment_type,
            job_type=job.employment_type,
            work_mode=job.work_mode,
            experience_required=SuperAdminDashboardService._range_value(
                job.experience_min,
                job.experience_max,
            ),
            industry=industry,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_range=salary_range,
            status=job.status,
            posted_date=job.created_at,
            expiry_date=job.application_deadline,
            created_by=job.created_by,
        )

    @staticmethod
    async def list_recent_registrations(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str],
        role: Optional[str],
        date_range: NormalizedDateRange | None = None,
    ) -> RecentRegistrationListResponse:
        rows, total = await SuperAdminDashboardRepository.list_recent_registrations(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            role=role,
            date_range=date_range,
        )

        items = []
        for user, user_role in rows:
            full_name = " ".join(
                part
                for part in [user.first_name, user.last_name]
                if part
            )
            items.append(
                RecentRegistrationItem(
                    user_id=user.user_id,
                    full_name=full_name,
                    email=user.email,
                    role=user_role.role_code,
                    status=user.user_status,
                    created_at=user.created_at,
                )
            )

        return RecentRegistrationListResponse(
            items=items,
            total=total,
            total_records=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def get_job_overview(
        session: AsyncSession,
    ) -> JobOverviewResponse:
        data = await SuperAdminDashboardRepository.get_job_overview(
            session=session,
        )
        return JobOverviewResponse(**data)

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str],
        company: Optional[str],
        recruiter: Optional[str],
        location: Optional[str],
        status: Optional[str],
        employment_type: Optional[str],
        work_mode: Optional[str],
        experience_level: Optional[str],
        industry: Optional[str],
        salary_min: Optional[float],
        salary_max: Optional[float],
        posted_date,
        expiry_date,
        date_range: NormalizedDateRange | None,
        sort_by: str,
        sort_order: str,
    ) -> SuperAdminJobListResponse:
        jobs, total = await SuperAdminDashboardRepository.list_jobs(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            company=company,
            recruiter=recruiter,
            location=location,
            status=status,
            employment_type=employment_type,
            work_mode=work_mode,
            experience_level=experience_level,
            industry=industry,
            salary_min=salary_min,
            salary_max=salary_max,
            posted_date=posted_date,
            expiry_date=expiry_date,
            date_range=date_range,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return SuperAdminJobListResponse(
            items=[SuperAdminDashboardService._job_item(row) for row in jobs],
            total=total,
            total_records=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def bulk_action_jobs(
        session: AsyncSession,
        job_ids: list[str],
        action: str,
        actor: Any,
        reason: Optional[str] = None,
    ) -> SuperAdminJobBulkActionResponse:
        unique_job_ids = list(dict.fromkeys(job_ids))
        if not unique_job_ids:
            return SuperAdminJobBulkActionResponse(
                action=action.upper(),
                requested=0,
                updated=0,
                job_ids=[],
            )

        actor_id = str(actor.get("user_id")) if isinstance(actor, dict) and actor.get("user_id") else None
        if action.lower() == "activate":
            await SuperAdminDashboardService._ensure_bulk_activate_within_plan_limits(
                session=session,
                job_ids=unique_job_ids,
            )
        updated = await SuperAdminDashboardRepository.bulk_update_jobs(
            session=session,
            job_ids=unique_job_ids,
            action=action,
            actor_id=actor_id,
            reason=reason,
        )

        action_label = {
            "activate": "Bulk Activate",
            "pause": "Bulk Pause",
            "close": "Bulk Close",
            "delete": "Delete",
        }[action.lower()]
        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action=action_label.replace(" ", "_").upper(),
            entity_type="Job",
            entity_id=",".join(unique_job_ids),
            description=f"{action_label} jobs: {updated} updated",
        )
        if action.lower() == "close" and updated:
            await NotificationService.create_for_super_admins(
                session,
                notification_type="JOB_CLOSED",
                title="Jobs closed",
                message=f"{updated} job(s) were closed by Super Admin.",
                entity_type="job",
                entity_id=",".join(unique_job_ids),
                target_route="/super-admin/jobs",
                metadata={"job_ids": unique_job_ids, "reason": reason},
                event_key=f"jobs_bulk_closed:{','.join(unique_job_ids)}",
                commit=True,
            )

        return SuperAdminJobBulkActionResponse(
            action=action.upper(),
            requested=len(unique_job_ids),
            updated=updated,
            job_ids=unique_job_ids,
        )

    @staticmethod
    def _export_rows(items: list[SuperAdminJobItem]) -> list[dict[str, Any]]:
        return [
            {
                "Job ID": item.job_id,
                "Job Title": item.job_title,
                "Company": item.company_name or "",
                "Recruiter": item.recruiter_name or "",
                "Status": item.status,
                "Job Type": item.employment_type,
                "Work Mode": item.work_mode or "",
                "Experience": item.experience_required or "",
                "Industry": item.industry or "",
                "Location": item.location or "",
                "Salary Min": item.salary_min if item.salary_min is not None else "",
                "Salary Max": item.salary_max if item.salary_max is not None else "",
                "Posted Date": item.posted_date.isoformat() if item.posted_date else "",
                "Expiry Date": item.expiry_date.isoformat() if item.expiry_date else "",
            }
            for item in items
        ]

    @staticmethod
    async def export_jobs(
        session: AsyncSession,
        export_format: str,
        actor: Any,
        **filters,
    ) -> tuple[bytes, str, str]:
        first_page = await SuperAdminDashboardService.list_jobs(
            session=session,
            page=1,
            page_size=1,
            **filters,
        )
        data = await SuperAdminDashboardService.list_jobs(
            session=session,
            page=1,
            page_size=max(first_page.total, 1),
            **filters,
        )
        rows = SuperAdminDashboardService._export_rows(data.items)
        headers = list(rows[0].keys()) if rows else [
            "Job ID", "Job Title", "Company", "Recruiter", "Status", "Job Type",
            "Work Mode", "Experience", "Industry", "Location", "Salary Min",
            "Salary Max", "Posted Date", "Expiry Date",
        ]

        normalized = export_format.lower()
        filename = f"super-admin-jobs.{normalized if normalized != 'excel' else 'xls'}"

        if normalized == "pdf":
            from reportlab.lib.pagesizes import landscape, letter
            from reportlab.pdfgen import canvas

            buffer = BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(36, 560, "Super Admin Jobs Overview")
            pdf.setFont("Helvetica", 8)
            y = 535
            for row in rows:
                line = " | ".join(str(row[key]) for key in headers[:8])
                pdf.drawString(36, y, line[:170])
                y -= 14
                if y < 36:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 8)
                    y = 560
            pdf.save()
            content = buffer.getvalue()
            media_type = "application/pdf"
        else:
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
            content = output.getvalue().encode("utf-8")
            media_type = "text/csv" if normalized == "csv" else "application/vnd.ms-excel"

        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action="EXPORT",
            entity_type="Job",
            description=f"Exported Super Admin jobs as {normalized.upper()}",
        )
        return content, filename, media_type

    @staticmethod
    async def list_users(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str],
        role: Optional[str],
        status: Optional[str],
        subscription: Optional[str],
        registered_from,
        registered_to,
        date_range: NormalizedDateRange | None,
        sort_by: str,
    ) -> SuperAdminUserListResponse:
        rows, total = await SuperAdminDashboardRepository.list_users(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            role=role,
            status=status,
            subscription=subscription,
            registered_from=registered_from,
            registered_to=registered_to,
            date_range=date_range,
            sort_by=sort_by,
        )

        items = []
        role_priority = (
            "ROLE_SUPER_ADMIN",
            "ROLE_ADMIN",
            "ROLE_EMPLOYER",
            "ROLE_RECRUITER",
            "ROLE_CANDIDATE",
        )

        for user, subscription_name in rows:
            name = " ".join(
                part for part in [user.first_name, user.last_name] if part
            )
            role_codes = {role.role_code for role in user.roles}
            display_role = next(
                (role_code for role_code in role_priority if role_code in role_codes),
                next(iter(sorted(role_codes)), ""),
            )
            items.append(
                SuperAdminUserItem(
                    user_id=user.user_id,
                    name=name,
                    email=user.email,
                    role=display_role,
                    status=user.user_status,
                    subscription=subscription_name,
                    registered_on=user.created_at,
                    last_login=user.last_login_at,
                )
            )

        return SuperAdminUserListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
