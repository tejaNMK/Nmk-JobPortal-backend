from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.schema.common import ResponseSchema, created_response
from app.schema.interview import (
    ScheduleInterviewRequest,
    ScheduleInterviewRoundsRequest,
    UpdateInterviewRequest,
)
from app.service.employer_service.interview_service import (
    InterviewService,
)
from app.repository.employer_repository.shortlisted_candidates_repo import (
    ShortlistedCandidatesRepo,
)
router = APIRouter(
    prefix="/employer/interviews",
    tags=["Interview Scheduling"],
)


def get_user_id(
    payload: dict = Depends(get_jwt_payload_401),
) -> UUID:

    raw_user_id = payload.get("user_id")

    if not raw_user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing user_id in token",
        )

    return UUID(str(raw_user_id))

async def get_employer_id(
    session: AsyncSession,
    user_id: UUID,
) -> str:

    employer_id = await ShortlistedCandidatesRepo.get_employer_id(
        session=session,
        user_id=user_id,
    )

    if not employer_id:
        raise HTTPException(
            status_code=403,
            detail="Employer profile not found.",
        )

    return employer_id


@router.post(
    "/schedule/{application_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
)
async def schedule_interview(
    application_id: str,
    request: ScheduleInterviewRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.schedule_interview(
        session=session,
        employer_id=employer_id,
        application_id=application_id,
        request=request,   
        performed_by=str(user_id),
    )

    return created_response(
        message="Interview scheduled successfully",
        data=result.model_dump(),
    )


@router.post(
    "/schedule/{application_id}/rounds",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
)
async def schedule_interview_rounds(
    application_id: str,
    request: ScheduleInterviewRoundsRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.schedule_interview_rounds(
        session=session,
        employer_id=employer_id,
        application_id=application_id,
        request=request,
        performed_by=str(user_id),
    )

    return created_response(
        message="Interview rounds scheduled successfully",
        data=[interview.model_dump() for interview in result],
    )


@router.get(
    "/{application_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_interview(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.get_interview(
        session=session,
        employer_id=employer_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interview details fetched successfully",
        data=result.model_dump(),
    )


@router.put(
    "/{interview_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_interview(
    interview_id: str,
    request: UpdateInterviewRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.update_interview(
        session=session,
        employer_id=employer_id,
        interview_id=interview_id,
        request=request,
        performed_by=str(user_id),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interview updated successfully",
        data=result.model_dump(),
    )


@router.patch(
    "/{interview_id}/cancel",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def cancel_interview(
    interview_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.cancel_interview(
        session=session,
        employer_id=employer_id,
        interview_id=interview_id,
        performed_by=str(user_id),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interview cancelled successfully",
        data=result.model_dump(),
    )

@router.patch(
    "/{interview_id}/complete",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def complete_interview(
    interview_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.complete_interview(
        session=session,
        employer_id=employer_id,
        interview_id=interview_id,
        performed_by=str(user_id),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interview marked as completed successfully",
        data=result.model_dump(),
    )

@router.patch(
    "/{interview_id}/no-show",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def mark_no_show(
    interview_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    employer_id = await get_employer_id(
        session=session,
        user_id=user_id,
    )

    result = await InterviewService.mark_no_show(
        session=session,
        employer_id=employer_id,
        interview_id=interview_id,
        performed_by=str(user_id),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate marked as No Show successfully",
        data=result.model_dump(),
    )
