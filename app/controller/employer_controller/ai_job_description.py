from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.controller.employer_controller.profile_helpers import get_existing_employer_profile
from app.dependencies.role_dependencies import employer_user_only
from app.schema.employer_ai_job_description import (
    AIJobDescriptionGenerateRequest,
    AIJobDescriptionImproveRequest,
    AIJobDescriptionRegenerateRequest,
)
from app.schema.common import ResponseSchema
from app.service.employer_service.ai_job_description_service import AIJobDescriptionService


router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post(
    "/generate-description",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Generate a complete ATS-friendly job description",
)
async def generate_description(
    request_body: AIJobDescriptionGenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await get_existing_employer_profile(session=session, payload=payload)
    result = await AIJobDescriptionService.generate_description(
        session=session,
        payload=payload,
        employer=employer,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Job description generated successfully",
        data=result.model_dump(),
    )


@router.post(
    "/improve-description",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Improve and ATS-optimize an existing job description",
)
async def improve_description(
    request_body: AIJobDescriptionImproveRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await get_existing_employer_profile(session=session, payload=payload)
    result = await AIJobDescriptionService.improve_description(
        session=session,
        payload=payload,
        employer=employer,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Job description improved successfully",
        data=result.model_dump(),
    )


@router.post(
    "/regenerate",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Regenerate one job description section",
)
async def regenerate_section(
    request_body: AIJobDescriptionRegenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await get_existing_employer_profile(session=session, payload=payload)
    result = await AIJobDescriptionService.regenerate_section(
        session=session,
        payload=payload,
        employer=employer,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Job description section regenerated successfully",
        data=result.model_dump(),
    )


@router.post(
    "/generate-description/stream",
    summary="Stream job description generation using server-sent events",
)
async def stream_generate_description(
    request_body: AIJobDescriptionGenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await get_existing_employer_profile(session=session, payload=payload)
    return StreamingResponse(
        AIJobDescriptionService.stream_generate_description(
            session=session,
            payload=payload,
            employer=employer,
            request=request_body,
        ),
        media_type="text/event-stream",
    )
