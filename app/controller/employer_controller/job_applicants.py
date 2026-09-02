from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema
from app.schema.job_applicants import (
    ApplicantFilterParams,
    EmployerApplicationStatusUpdateRequest,
)
from app.service.employer_service.job_applicants_service import (
    JobApplicantsService,
)

router = APIRouter(
    prefix="/employer/job-applicants",
    tags=["Job Applicants"],
    dependencies=[Depends(employer_user_only)],
)

applications_router = APIRouter(
    prefix="/employer/applications",
    tags=["Employer Applications"],
    dependencies=[Depends(employer_user_only)],
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


@router.get(
    "",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def list_applicants(
    job_id: Optional[str] = Query(
        default=None,
        max_length=100,
    ),
    search: Optional[str] = Query(
        default=None,
        max_length=100,
    ),
    status: Optional[str] = Query(
        default=None,
        max_length=50,
    ),
    sort_by: Optional[str] = Query(
        default=None,
        max_length=50,
    ),
    sort: Optional[str] = Query(
        default=None,
        max_length=50,
        description="Alias for sort_by. Use best_match to rank applicants by AI fit.",
    ),
    ai_rank: bool = Query(
        default=False,
        description="Set true when the employer clicks AI Rank Applicants.",
    ),
    sort_order: str = Query(
        default="desc",
        pattern="(?i)^(asc|desc)$",
    ),
    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    filters = ApplicantFilterParams(
        job_id=job_id,
        search=search,
        status=status,
        sort_by=sort_by or sort,
        sort_order=sort_order.lower(),
        ai_rank=ai_rank,
        page=page,
        page_size=page_size,
    )

    result = await JobApplicantsService.list_applicants(
        session=session,
        user_id=user_id,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Applicants fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{application_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_applicant_profile(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await JobApplicantsService.get_applicant_profile(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Applicant profile fetched successfully",
        data=result.model_dump(),
    )


@router.patch(
    "/{application_id}/status",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_application_status(
    application_id: str,
    payload: EmployerApplicationStatusUpdateRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await JobApplicantsService.update_application_status(
        session=session,
        user_id=user_id,
        application_id=application_id,
        payload=payload,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Application status updated successfully",
        data=result.model_dump(),
    )


@applications_router.patch(
    "/{application_id}/status",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def update_employer_application_status(
    application_id: str,
    payload: EmployerApplicationStatusUpdateRequest,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await JobApplicantsService.update_application_status(
        session=session,
        user_id=user_id,
        application_id=application_id,
        payload=payload,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Application status updated successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{application_id}/resume",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def get_resume(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):

    result = await JobApplicantsService.get_resume(
        session=session,
        user_id=user_id,
        application_id=application_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Resume fetched successfully",
        data=result.model_dump(),
    )


@router.get(
    "/{application_id}/resume/download-file",
)
async def download_resume_file(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    content, filename, content_type = await JobApplicantsService.get_resume_file(
        session=session,
        user_id=user_id,
        application_id=application_id,
        count_as_download=True,
    )

    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename.replace(chr(34), "")}"'},
    )


@router.get(
    "/{application_id}/resume/preview-file",
)
async def preview_resume_file(
    application_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_db),
):
    content, filename, content_type = await JobApplicantsService.get_resume_file(
        session=session,
        user_id=user_id,
        application_id=application_id,
        count_as_download=False,
    )

    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename.replace(chr(34), "")}"'},
    )
