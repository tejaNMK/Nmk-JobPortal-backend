from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.super_admin.company_approval_repo import CompanyApprovalRepository
from app.schema.super_admin.company_approval import (
    CompanyApprovalActionResponse,
    CompanyApprovalHistoryItem,
    CompanyApprovalItem,
    CompanyApprovalListResponse,
    LatestCompanyApprovalItem,
    LatestCompanyApprovalResponse,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService
from app.utils.date_range import NormalizedDateRange


class CompanyApprovalService:
    @staticmethod
    def _item(company, employer, user) -> CompanyApprovalItem:
        employer_name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        )
        return CompanyApprovalItem(
            company_id=company.company_id,
            company_uuid=company.id,
            company_name=company.company_name,
            employer_id=employer.id,
            employer_user_id=user.user_id,
            employer_name=employer_name,
            employer_email=user.email,
            industry=company.industry or employer.industry,
            location=company.location or employer.company_location,
            verification_status=company.verification_status,
            rejection_reason=company.rejection_reason or employer.rejection_reason,
            submitted_at=company.created_at,
            approved_at=company.approved_at,
            rejected_at=company.rejected_at,
        )

    @staticmethod
    async def list_company_approvals(
        session: AsyncSession,
        page: int,
        page_size: int,
        search,
        company,
        status,
        start_date,
        end_date,
        sort_by: str,
        sort_order: str,
        date_range: NormalizedDateRange | None = None,
    ) -> CompanyApprovalListResponse:
        rows, total = await CompanyApprovalRepository.list_company_approvals(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            company=company,
            status=status,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return CompanyApprovalListResponse(
            items=[CompanyApprovalService._item(*row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def list_pending(
        session: AsyncSession,
        page: int,
        page_size: int,
        search,
        company,
        start_date,
        end_date,
        sort_by: str,
        sort_order: str,
        date_range: NormalizedDateRange | None = None,
    ) -> CompanyApprovalListResponse:
        rows, total = await CompanyApprovalRepository.list_pending(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            company=company,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return CompanyApprovalListResponse(
            items=[CompanyApprovalService._item(*row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def list_history(
        session: AsyncSession,
        page: int,
        page_size: int,
        search,
        company,
        status,
        start_date,
        end_date,
        sort_by: str,
        sort_order: str,
        date_range: NormalizedDateRange | None = None,
    ) -> CompanyApprovalListResponse:
        rows, total = await CompanyApprovalRepository.list_history(
            session=session,
            page=page,
            page_size=page_size,
            search=search,
            company=company,
            status=status,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        items = []
        for row in rows:
            item = CompanyApprovalService._item(*row)
            items.append(
                CompanyApprovalHistoryItem(
                    **item.model_dump(),
                    action_date=item.approved_at or item.rejected_at,
                )
            )
        return CompanyApprovalListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def approve_company(
        session: AsyncSession,
        company_id: str,
        actor,
    ) -> CompanyApprovalActionResponse:
        row = await CompanyApprovalRepository.get_by_company_id(
            session=session,
            company_id=company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found.")

        company, employer, _user = row
        if company.verification_status == "APPROVED" or employer.is_verified == 1:
            raise HTTPException(status_code=400, detail="Company is already approved.")

        company, _employer = await CompanyApprovalRepository.update_verification(
            session=session,
            company=company,
            employer=employer,
            status="APPROVED",
        )
        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action="COMPANY_APPROVED",
            entity_type="Company",
            entity_id=company.company_id,
            description=f"Approved company {company.company_name}",
        )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="COMPANY_APPROVED",
            title="Company approved",
            message=f"{company.company_name} was approved.",
            entity_type="company",
            entity_id=company.company_id,
            target_route=f"/super-admin/company-approvals?company_id={company.company_id}",
            event_key=f"company_approved:{company.company_id}:{company.approved_at}",
            commit=True,
        )
        return CompanyApprovalActionResponse(
            company_id=company.company_id,
            verification_status=company.verification_status,
            approved_at=company.approved_at,
        )

    @staticmethod
    async def reject_company(
        session: AsyncSession,
        company_id: str,
        reason: str,
        actor,
    ) -> CompanyApprovalActionResponse:
        if not reason or not reason.strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required.")

        row = await CompanyApprovalRepository.get_by_company_id(
            session=session,
            company_id=company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found.")

        company, employer, _user = row
        company, _employer = await CompanyApprovalRepository.update_verification(
            session=session,
            company=company,
            employer=employer,
            status="REJECTED",
            reason=reason.strip(),
        )
        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action="COMPANY_REJECTED",
            entity_type="Company",
            entity_id=company.company_id,
            description=f"Rejected company {company.company_name}",
        )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="COMPANY_REJECTED",
            title="Company rejected",
            message=f"{company.company_name} was rejected.",
            entity_type="company",
            entity_id=company.company_id,
            target_route=f"/super-admin/company-approvals?company_id={company.company_id}",
            event_key=f"company_rejected:{company.company_id}:{company.rejected_at}",
            commit=True,
        )
        return CompanyApprovalActionResponse(
            company_id=company.company_id,
            verification_status=company.verification_status,
            rejected_at=company.rejected_at,
            rejection_reason=company.rejection_reason,
        )

    @staticmethod
    async def latest_company_approvals(
        session: AsyncSession,
        limit: int,
        date_range: NormalizedDateRange | None = None,
    ) -> LatestCompanyApprovalResponse:
        rows, _total = await CompanyApprovalRepository.list_company_approvals(
            session=session,
            page=1,
            page_size=limit,
            date_range=date_range,
            sort_by="created_at",
            sort_order="desc",
        )
        items = []
        for company, _employer, user in rows:
            employer_name = " ".join(
                part for part in [user.first_name, user.last_name] if part
            )
            items.append(
                LatestCompanyApprovalItem(
                    company_id=company.company_id,
                    company_name=company.company_name,
                    employer_name=employer_name,
                    verification_status=company.verification_status,
                    submitted_at=company.created_at,
                    approved_at=company.approved_at,
                    rejected_at=company.rejected_at,
                )
            )
        return LatestCompanyApprovalResponse(items=items)
