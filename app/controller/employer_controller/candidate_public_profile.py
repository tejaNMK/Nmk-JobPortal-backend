from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.service.candidate_service import CandidateProfileService
from app.service.subscription.subscription_validator import SubscriptionValidator


router = APIRouter(
    prefix="/employer",
    tags=["Employer Candidate Public Profile"],
)


async def _fetch_candidate_public_profile(
    candidate_id: str,
    payload: dict,
    session: AsyncSession,
) -> ResponseSchema:
    validator = SubscriptionValidator(
        session=session,
        user_id=payload.get("user_id"),
        role="EMPLOYER",
    )
    await validator.require_feature("candidate_search")
    # Recruiters/employers are gated by the "Recruiter search" toggle
    # (searchable_flag), independent of the candidate's "Public link"
    # toggle (profile_visibility).
    result = await CandidateProfileService.get_candidate_detail_for_employer(
        session=session,
        candidate_id=candidate_id,
        employer_user_id=UUID(str(payload["user_id"])) if payload.get("user_id") else None,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate public profile fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/candidates/{candidate_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def employer_get_candidate_public_profile_by_id(
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    return await _fetch_candidate_public_profile(candidate_id, payload, session)


@router.get(
    "/candidates/{candidate_id}/public-profile",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def employer_get_candidate_public_profile(
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    return await _fetch_candidate_public_profile(candidate_id, payload, session)


@router.get(
    "/candidates/{candidate_id}/public-profile-with-view",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def employer_get_candidate_public_profile_with_view(
    candidate_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    # Fallback for clients that want an authenticated endpoint; still
    # returns the same safe profile fields, gated by searchable_flag.
    return await _fetch_candidate_public_profile(candidate_id, payload, session)
