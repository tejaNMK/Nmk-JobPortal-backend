from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException

from app.model.employer_model.company_profile import CompanyProfile
from app.repository.candidate_repository.candidate_following_repo import CandidateFollowingRepo
from app.schema.candidate_following import (
    BulkFollowResponse,
    FollowActionResponse,
    FollowedCompanyItem,
    FollowingListResponse,
    NotifyPreferenceResponse,
    SmartSuggestionGroup,
    SmartSuggestionsResponse,
    SuggestedCompany,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _company_summary(company: CompanyProfile) -> SuggestedCompany:
    return SuggestedCompany(
        company_id=company.company_id,
        name=company.company_name,
        industry=company.industry,
        location=company.location,
        logo=company.logo_url or company.logo_path,
    )


class CandidateFollowingService:

    @staticmethod
    async def _get_candidate_id(session: AsyncSession, user_id: UUID) -> str:
        profile = await CandidateFollowingRepo.get_candidate_profile(session, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        return profile.candidate_id

    @staticmethod
    async def _get_candidate_profile(session: AsyncSession, user_id: UUID):
        profile = await CandidateFollowingRepo.get_candidate_profile(session, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        return profile

    # ── List ─────────────────────────────────────────────────────────────────
    @staticmethod
    async def list_followings(
        session: AsyncSession,
        user_id: UUID,
        search: Optional[str],
        sort_by: str,
        page: int,
        page_size: int,
    ) -> FollowingListResponse:
        profile = await CandidateFollowingService._get_candidate_profile(session, user_id)
        candidate_id = profile.candidate_id

        rows, total = await CandidateFollowingRepo.list_followed(
            session, candidate_id, search, sort_by, page, page_size
        )
        company_ids = [row.company_id for row in rows]
        open_jobs_map = await CandidateFollowingRepo.fetch_open_jobs_count_by_company(session, company_ids)

        items = [
            FollowedCompanyItem(
                company_id=row.company_id,
                name=row.company.company_name if row.company else "",
                industry=row.company.industry if row.company else None,
                location=row.company.location if row.company else None,
                logo=(row.company.logo_url or row.company.logo_path) if row.company else None,
                open_jobs_count=open_jobs_map.get(row.company_id, 0),
                followed_at=row.followed_at,
            )
            for row in rows
            if row.company
        ]

        return FollowingListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            notify_enabled=profile.follow_notifications_enabled,
        )

    # ── Follow / unfollow ────────────────────────────────────────────────────
    @staticmethod
    async def follow_company(session: AsyncSession, user_id: UUID, company_id: str) -> FollowActionResponse:
        candidate_id = await CandidateFollowingService._get_candidate_id(session, user_id)

        company = await CandidateFollowingRepo.get_public_company(session, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        existing = await CandidateFollowingRepo.get_following_row(session, candidate_id, company_id)
        if existing and not existing.is_deleted:
            return FollowActionResponse(
                message="You are already following this company",
                company_id=company_id,
                is_following=True,
            )

        if existing and existing.is_deleted:
            await CandidateFollowingRepo.restore_following(session, existing)
        else:
            await CandidateFollowingRepo.create_following(session, candidate_id, company_id)

        return FollowActionResponse(
            message="Company followed successfully",
            company_id=company_id,
            is_following=True,
        )

    @staticmethod
    async def unfollow_company(session: AsyncSession, user_id: UUID, company_id: str) -> FollowActionResponse:
        candidate_id = await CandidateFollowingService._get_candidate_id(session, user_id)

        existing = await CandidateFollowingRepo.get_following_row(session, candidate_id, company_id)
        if not existing or existing.is_deleted:
            raise HTTPException(status_code=404, detail="You are not following this company")

        await CandidateFollowingRepo.soft_delete_following(session, existing)

        return FollowActionResponse(
            message="Company unfollowed successfully",
            company_id=company_id,
            is_following=False,
        )

    @staticmethod
    async def bulk_follow(session: AsyncSession, user_id: UUID, company_ids: List[str]) -> BulkFollowResponse:
        candidate_id = await CandidateFollowingService._get_candidate_id(session, user_id)

        unique_ids = list(dict.fromkeys(company_ids))
        companies = await CandidateFollowingRepo.fetch_companies_by_ids(session, unique_ids)
        public_company_ids = {c.company_id for c in companies if c.is_public}

        followed: List[str] = []
        already_following: List[str] = []
        not_found: List[str] = []

        for company_id in unique_ids:
            if company_id not in public_company_ids:
                not_found.append(company_id)
                continue

            existing = await CandidateFollowingRepo.get_following_row(session, candidate_id, company_id)
            if existing and not existing.is_deleted:
                already_following.append(company_id)
                continue

            if existing and existing.is_deleted:
                await CandidateFollowingRepo.restore_following(session, existing)
            else:
                await CandidateFollowingRepo.create_following(session, candidate_id, company_id)
            followed.append(company_id)

        return BulkFollowResponse(
            followed=followed,
            already_following=already_following,
            not_found=not_found,
        )

    # ── Smart suggestions ────────────────────────────────────────────────────
    @staticmethod
    async def get_smart_suggestions(session: AsyncSession, user_id: UUID) -> SmartSuggestionsResponse:
        candidate_id = await CandidateFollowingService._get_candidate_id(session, user_id)
        followed_ids = await CandidateFollowingRepo.list_followed_company_ids(session, candidate_id)

        groups: List[SmartSuggestionGroup] = []

        top_title = await CandidateFollowingRepo.fetch_top_candidate_job_title(session, candidate_id)
        if top_title:
            companies = await CandidateFollowingRepo.fetch_companies_hiring_for_title(
                session, top_title, followed_ids, limit=6
            )
            if companies:
                groups.append(
                    SmartSuggestionGroup(
                        group_key="hiring-for-role",
                        title=f"Companies hiring for {top_title} roles",
                        subtitle="Based on your saved jobs and search history.",
                        action="FOLLOW_ALL",
                        companies=[_company_summary(c) for c in companies],
                    )
                )

        remote_companies = await CandidateFollowingRepo.fetch_companies_expanding_remote(
            session, followed_ids, limit=6
        )
        if remote_companies:
            groups.append(
                SmartSuggestionGroup(
                    group_key="expanding-remote",
                    title="Companies expanding remote teams",
                    subtitle=f"{len(remote_companies)} companies align with your preferences.",
                    action="REVIEW",
                    companies=[_company_summary(c) for c in remote_companies],
                )
            )

        return SmartSuggestionsResponse(groups=groups)

    # ── Notify preference ────────────────────────────────────────────────────
    @staticmethod
    async def set_notify_preference(session: AsyncSession, user_id: UUID, enabled: bool) -> NotifyPreferenceResponse:
        profile = await CandidateFollowingService._get_candidate_profile(session, user_id)
        profile = await CandidateFollowingRepo.set_notify_preference(session, profile, enabled)
        return NotifyPreferenceResponse(notify_enabled=profile.follow_notifications_enabled)