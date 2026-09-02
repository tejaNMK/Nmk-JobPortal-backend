from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.candidate_following import (
    BulkFollowRequest,
    FollowingSortBy,
    NotifyPreferenceUpdate,
)
from app.schema.common import ResponseSchema, success_response
from app.service.candidate_following_service import CandidateFollowingService

router = APIRouter(
    prefix="/candidate/followings",
    tags=["My Followings"],
)


def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


@router.get("", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_followings(
    search: Optional[str] = Query(default=None, max_length=100),
    sort_by: FollowingSortBy = Query(default="FOLLOWED_DATE_DESC"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.list_followings(
        session, user_id, search, sort_by, page, page_size
    )
    return success_response(
        message="Followed companies fetched successfully",
        data=result.model_dump(),
    )


@router.get("/suggestions", response_model=ResponseSchema, response_model_exclude_none=True)
async def get_smart_suggestions(
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.get_smart_suggestions(session, user_id)
    return success_response(
        message="Smart suggestions fetched successfully",
        data=result.model_dump(),
    )


@router.post("/bulk-follow", response_model=ResponseSchema, response_model_exclude_none=True)
async def bulk_follow_companies(
    body: BulkFollowRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.bulk_follow(session, user_id, body.company_ids)
    return success_response(
        message="Bulk follow processed",
        data=result.model_dump(),
    )


@router.patch("/notify-preference", response_model=ResponseSchema, response_model_exclude_none=True)
async def update_notify_preference(
    body: NotifyPreferenceUpdate,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.set_notify_preference(session, user_id, body.enabled)
    return success_response(
        message="Notify preference updated successfully",
        data=result.model_dump(),
    )


@router.post("/{company_id}", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def follow_company(
    company_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.follow_company(session, user_id, company_id)
    return ResponseSchema(
        success=True,
        status=201,
        message=result.message,
        data=result.model_dump(),
    )


@router.delete("/{company_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def unfollow_company(
    company_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateFollowingService.unfollow_company(session, user_id, company_id)
    return success_response(
        message=result.message,
        data=result.model_dump(),
    )