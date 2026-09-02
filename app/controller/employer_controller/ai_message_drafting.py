from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.model.employer_model.employer_profile import EmployerProfile
from app.schema.employer_ai_message_drafting import (
    AIMessageDraftRequest,
    AIMessageImproveRequest,
)
from app.schema.common import ResponseSchema
from app.service.employer_service.ai_message_drafting_service import (
    AIMessageDraftingService,
)


router = APIRouter(
    prefix="/employer/ai",
    tags=["Employer AI"],
)


async def _get_existing_employer_profile(
    session: AsyncSession,
    payload: dict,
) -> EmployerProfile:
    result = await session.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
    )
    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")
    return employer


@router.post(
    "/message-draft",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Generate an AI-assisted candidate message draft",
)
async def generate_ai_message_draft(
    request_body: AIMessageDraftRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
    result = await AIMessageDraftingService.generate_draft(
        session=session,
        payload=payload,
        employer=employer,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI message draft generated successfully",
        data=result.model_dump(),
    )


@router.post(
    "/message-improve",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Improve an existing recruiter message with AI",
)
async def improve_ai_message_draft(
    request_body: AIMessageImproveRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
    result = await AIMessageDraftingService.improve_message(
        session=session,
        payload=payload,
        employer=employer,
        request=request_body,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="AI message improved successfully",
        data=result.model_dump(),
    )
