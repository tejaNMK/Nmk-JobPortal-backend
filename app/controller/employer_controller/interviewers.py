from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema, created_response
from app.schema.interview import (
    InterviewerCreateRequest,
    InterviewerUpdateRequest,
)
from app.service.employer_service.interview_service import InterviewerService


router = APIRouter(
    prefix="/employer/interviewers",
    tags=["Employer Interviewers"],
    dependencies=[Depends(employer_user_only)],
)


@router.post(
    "",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
)
async def create_interviewer(
    request: InterviewerCreateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await InterviewerService.create_interviewer(
        session=session,
        request=request,
        performed_by=payload.get("user_id"),
    )

    return created_response(
        message="Interviewer created successfully",
        data=result.model_dump(),
    )


@router.get(
    "",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def list_interviewers(
    search: Optional[str] = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    result = await InterviewerService.list_interviewers(
        session=session,
        search=search,
        page=page,
        page_size=page_size,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interviewers fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{interviewer_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_interviewer(
    interviewer_id: str,
    session: AsyncSession = Depends(get_db),
):
    result = await InterviewerService.get_interviewer(
        session=session,
        interviewer_id=interviewer_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interviewer fetched successfully",
        data=result.model_dump(),
    )


@router.put(
    "/{interviewer_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_interviewer(
    interviewer_id: str,
    request: InterviewerUpdateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    result = await InterviewerService.update_interviewer(
        session=session,
        interviewer_id=interviewer_id,
        request=request,
        performed_by=payload.get("user_id"),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interviewer updated successfully",
        data=result.model_dump(),
    )


@router.delete(
    "/{interviewer_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def delete_interviewer(
    interviewer_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    await InterviewerService.delete_interviewer(
        session=session,
        interviewer_id=interviewer_id,
        performed_by=payload.get("user_id"),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Interviewer deleted successfully",
        data={},
    )
