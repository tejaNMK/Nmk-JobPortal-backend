from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, HTTPException, UploadFile

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.job_application_schema import (
    ApplicationNoteCreateSchema,
    ApplicationNoteUpdateSchema,
    ApplicationSource,
    ApplicationStatus,
    InterviewLoopDateSchema,
    JobApplicationCreateSchema,
    JobApplicationFilterParams,
    JobApplicationStatusUpdateSchema,
    NextStepUpsertSchema,
)
from app.schema.common import ResponseSchema, success_response
from app.service.job_application_service import JobApplicationService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/candidate/applications",
    tags=["My Job Applications"],
)

template_router = APIRouter(
    prefix="/candidate/my-job-applications",
    tags=["My Job Applications"],
)


def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


@router.post("", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def apply_for_job(body: JobApplicationCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.apply_for_job(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=201,
        message=result["message"],
        data=result
    )
    


@router.post("/with-resume", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def apply_for_job_with_resume(
    job_id: str = Form(...),
    cover_letter_text: Optional[str] = Form(default=None, max_length=5000),
    source: ApplicationSource = Form(default="Jobs Portal"),
    referral_contact: Optional[str] = Form(default=None, max_length=255),
    resume: UploadFile = File(...),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    contents = await resume.read()
    body = JobApplicationCreateSchema(
        job_id=job_id,
        cover_letter_text=cover_letter_text,
        source=source,
        referral_contact=referral_contact,
    )
    result = await JobApplicationService.apply_for_job_with_resume_upload(
        session=session,
        user_id=user_id,
        data=body,
        filename=resume.filename,
        content_type=resume.content_type,
        contents=contents,
    )
    return ResponseSchema(
        success=True,
        status=201,
        message=result["message"],
        data=result
    )


@router.get("", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_applications(
    status: Optional[ApplicationStatus] = Query(default=None),
    source: Optional[ApplicationSource] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: Literal[
        "APPLIED_DATE_DESC",
        "APPLIED_DATE_ASC",
        "JOB_TITLE_ASC",
        "JOB_TITLE_DESC",
        "STATUS_ASC",
        "STATUS_DESC",
    ] = Query(default="APPLIED_DATE_DESC"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    filters = JobApplicationFilterParams(
        status=status,
        source=source,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    result = await JobApplicationService.list_applications(session, user_id, filters)
    return ResponseSchema(
        success=True,
        status=200,
        message="Applications fetched successfully",
        data=result.model_dump()
    )


@router.get("/my-job-applications", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_my_job_applications(
    status: Optional[ApplicationStatus] = Query(default=None),
    source: Optional[ApplicationSource] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: Literal[
        "APPLIED_DATE_DESC",
        "APPLIED_DATE_ASC",
        "JOB_TITLE_ASC",
        "JOB_TITLE_DESC",
        "STATUS_ASC",
        "STATUS_DESC",
    ] = Query(default="APPLIED_DATE_DESC"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    filters = JobApplicationFilterParams(
        status=status,
        source=source,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    result = await JobApplicationService.list_applications(session, user_id, filters)
    return ResponseSchema(
        success=True,
        status=200,
        message="My job applications fetched successfully",
        data=result.model_dump()
    )


@template_router.get("", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_template_my_job_applications(
    status: Optional[ApplicationStatus] = Query(default=None),
    source: Optional[ApplicationSource] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    sort_by: Literal[
        "APPLIED_DATE_DESC",
        "APPLIED_DATE_ASC",
        "JOB_TITLE_ASC",
        "JOB_TITLE_DESC",
        "STATUS_ASC",
        "STATUS_DESC",
    ] = Query(default="APPLIED_DATE_DESC"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    filters = JobApplicationFilterParams(
        status=status,
        source=source,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    result = await JobApplicationService.list_applications(session, user_id, filters)
    return ResponseSchema(
        success=True,
        status=200,
        message="My job applications fetched successfully",
        data=result.model_dump()
    )


@router.get("/next-steps", response_model=ResponseSchema, response_model_exclude_none=True)
async def get_next_steps(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.get_next_steps_panel(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Next steps fetched successfully",
        data=result.model_dump()
    )


@router.get("/{application_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def get_application_detail(application_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.get_application_detail(session, user_id, application_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Application fetched successfully",
        data=result.model_dump()
    )


@router.patch("/{application_id}/status", response_model=ResponseSchema, response_model_exclude_none=True)
async def update_application_status(application_id: str, body: JobApplicationStatusUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.update_status(session, user_id, application_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.put("/{application_id}/next-step", response_model=ResponseSchema, response_model_exclude_none=True)
async def upsert_next_step(application_id: str, body: NextStepUpsertSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.upsert_next_step(session, user_id, application_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/{application_id}/interview-loop", response_model=ResponseSchema, response_model_exclude_none=True)
async def set_interview_loop_date(application_id: str, body: InterviewLoopDateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.set_interview_loop_date(session, user_id, application_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.post("/{application_id}/nudge", response_model=ResponseSchema, response_model_exclude_none=True)
async def send_nudge(application_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.send_nudge(session, user_id, application_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/{application_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def withdraw_application(application_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.withdraw_application(session, user_id, application_id)

    return success_response(message=result["message"])

@router.get("/{application_id}/notes", response_model=ResponseSchema, response_model_exclude_none=True)
async def get_notes(application_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.get_notes(session, user_id, application_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Notes fetched successfully",
        data=[n.model_dump() for n in result]
    )


@router.post("/{application_id}/notes", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def add_note(application_id: str, body: ApplicationNoteCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.add_note(session, user_id, application_id, body)
    return ResponseSchema(
        success=True,
        status=201,
        message="Note added successfully",
        data=result.model_dump()
    )


@router.patch("/{application_id}/notes/{note_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def update_note(application_id: str, note_id: str, body: ApplicationNoteUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.update_note(session, user_id, application_id, note_id, body)
    return success_response(message=result["message"])


@router.delete("/{application_id}/notes/{note_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def delete_note(application_id: str, note_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await JobApplicationService.delete_note(session, user_id, application_id, note_id)
    return success_response(message=result["message"])