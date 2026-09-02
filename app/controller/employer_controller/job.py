from __future__ import annotations

import json
import logging
from typing import Any, Optional, Literal
from uuid import uuid4


from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.config import commit_rollback, get_db

logger = logging.getLogger(__name__)


class _DbProxy:
   
    async def execute(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("db proxy is not configured")


db: Any = _DbProxy()


def _use_legacy_db_proxy() -> bool:
    if db is None or not hasattr(db, "execute"):
        return False
    if isinstance(db, _DbProxy):
        execute = getattr(db, "execute")
        return getattr(execute, "__qualname__", None) != "_DbProxy.execute"
    return True


from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.model.employer_model.employer_profile import EmployerProfile
from app.schema.employer_ai_job_description import (
    AIJobDescriptionGenerateRequest,
    AIJobDescriptionImproveRequest,
    AIJobDescriptionRegenerateRequest,
)
from app.schema.job import (
    CloseJobRequest,
    CloseJobResponse,
    JobListFiltersSchema,
    MAX_JOB_DESCRIPTION_LENGTH,
    PostJobRequestSchema,
    PostJobResponseSchema,
    ReopenJobResponse,
    ReopenJobResponseData,
    UpdateJobRequestSchema,
)




from app.schema.common import ResponseSchema, created_response
from app.controller.employer_controller.profile_helpers import (
    get_existing_employer_profile as _get_existing_employer_profile,
)
from app.service.employer_service.ai_job_description_service import AIJobDescriptionService
from app.service.employer_service.job_service import JobService, delete_job_service
from app.service.document_text_extraction_service import DocumentTextExtractionService


router = APIRouter(
    prefix="/jobs",
    tags=["My Jobs"],
)

employer_router = APIRouter(
    prefix="/jobs",
    tags=["My Jobs"],
)


_JOB_FORM_FIELDS = {
    "job_title",
    "job_description",
    "employment_type",
    "experience_required",
    "location",
    "country_id",
    "location_id",
    "custom_city",
    "work_mode",
    "salary_range",
    "salary_currency",
    "salary_period",
    "number_of_openings",
    "application_deadline",
    "company_name",
    "contact_email",
    "job_category",
    "seniority_level",
    "team",
    "team_size",
    "education",
    "application_instructions",
    "working_hours",
    "office_location",
    "map_url",
    "status",
}

_JOB_LIST_FORM_FIELDS = {
    "responsibilities",
    "requirements",
    "benefits",
}

_JOB_POST_JSON_EXAMPLE = {
    "job_title": "IT Delivery Manager - Epicor ERP",
    "job_description": "Lead cross-functional delivery for Epicor ERP initiatives.",
    "employment_type": "FULL_TIME",
    "experience_required": "5-8",
    "location": "Bangkok, Thailand",
    "country_id": "country-id-for-thailand",
    "location_id": "location-id-for-bangkok",
    "custom_city": None,
    "work_mode": "HYBRID",
    "skills": ["Epicor ERP", "Agile delivery", "Stakeholder management"],
    "salary_range": "500-3000",
    "salary_currency": "USD",
    "salary_period": "Monthly",
    "number_of_openings": 1,
    "application_deadline": "2099-12-31T23:59:59+00:00",
    "company_name": "Forum International",
    "contact_email": "hr@forum.example",
    "job_category": "Product & Engineering",
    "seniority_level": "Lead / Manager",
    "team": "Product Delivery",
    "team_size": "25+ collaborators",
    "education": "Master's preferred",
    "responsibilities": [
        "Own the roadmap for Epicor ERP releases",
        "Mentor scrum leads and coordinate delivery ceremonies",
    ],
    "requirements": [
        "5+ years leading enterprise software implementations",
        "Strong communication and stakeholder management skills",
    ],
    "benefits": [
        "Annual bonus",
        "Hybrid work flexibility",
        "Private medical cover",
    ],
    "application_instructions": "Attach your updated resume and share 2-3 project highlights.",
    "working_hours": "Monday - Friday, 9am-5pm",
    "office_location": "Dubai, United Arab Emirates",
    "map_url": "https://maps.google.com/?q=Dubai",
    "status": "PUBLISHED",
}

_JOB_MULTIPART_SCHEMA = {
    "type": "object",
    "properties": {
        "job_title": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["job_title"]},
        "job_description": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["job_description"]},
        "job_description_document": {
            "type": "string",
            "format": "binary",
            "description": (
                "Optional PDF, DOCX, or DOC upload. Max 5 MB. "
                "File name max 120 characters. Extracted text must be readable "
                "and no more than 5000 characters. Ignored when job_description is provided."
            ),
        },
        "employment_type": {"type": "string", "example": "FULL_TIME"},
        "experience_required": {"type": "string", "example": "5-8"},
        "location": {
            "type": "string",
            "description": "Backward-compatible display location. When country_id plus location_id/custom_city is sent, the API resolves this automatically.",
            "example": _JOB_POST_JSON_EXAMPLE["location"],
        },
        "country_id": {
            "type": "string",
            "nullable": True,
            "description": "Selected country id from GET /master-data/countries.",
            "example": "country-id-for-thailand",
        },
        "location_id": {
            "type": "string",
            "nullable": True,
            "description": "Selected city/location id from GET /master-data/countries/{country_id}/locations.",
            "example": "location-id-for-bangkok",
        },
        "custom_city": {
            "type": "string",
            "nullable": True,
            "description": "Free-text city when the city is not available in the country locations list.",
            "example": "Chiang Rai",
        },
        "work_mode": {"type": "string", "example": "HYBRID"},
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
            "example": _JOB_POST_JSON_EXAMPLE["skills"],
        },
        "salary_range": {"type": "string", "example": "500-3000"},
        "salary_currency": {"type": "string", "example": "USD"},
        "salary_period": {"type": "string", "example": "Monthly"},
        "number_of_openings": {"type": "integer", "example": 1},
        "application_deadline": {
            "type": "string",
            "format": "date-time",
            "example": _JOB_POST_JSON_EXAMPLE["application_deadline"],
        },
        "company_name": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["company_name"]},
        "contact_email": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["contact_email"]},
        "job_category": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["job_category"]},
        "seniority_level": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["seniority_level"]},
        "team": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["team"]},
        "team_size": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["team_size"]},
        "education": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["education"]},
        "responsibilities": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 300},
            "example": _JOB_POST_JSON_EXAMPLE["responsibilities"],
        },
        "requirements": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 300},
            "example": _JOB_POST_JSON_EXAMPLE["requirements"],
        },
        "benefits": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 80},
            "example": _JOB_POST_JSON_EXAMPLE["benefits"],
        },
        "application_instructions": {
            "type": "string",
            "example": _JOB_POST_JSON_EXAMPLE["application_instructions"],
        },
        "working_hours": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["working_hours"]},
        "office_location": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["office_location"]},
        "map_url": {"type": "string", "example": _JOB_POST_JSON_EXAMPLE["map_url"]},
        "status": {"type": "string", "example": "PUBLISHED"},
    },
    "required": [
        "job_title",
        "job_description",
        "employment_type",
        "experience_required",
        "work_mode",
        "skills",
        "number_of_openings",
        "company_name",
        "contact_email",
    ],
}

_POST_JOB_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": PostJobRequestSchema.model_json_schema(),
                "example": _JOB_POST_JSON_EXAMPLE,
            },
            "multipart/form-data": {
                "schema": _JOB_MULTIPART_SCHEMA,
            },
        },
    },
}

_PUT_JOB_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": UpdateJobRequestSchema.model_json_schema(),
                "example": {
                    "job_title": "Senior IT Delivery Manager - Epicor ERP",
                    "job_category": "Product & Engineering",
                    "seniority_level": "Senior Manager",
                    "responsibilities": [
                        "Lead delivery governance",
                        "Report portfolio health metrics",
                    ],
                    "benefits": ["Hybrid work flexibility", "Learning stipend"],
                    "status": "PUBLISHED",
                },
            },
            "multipart/form-data": {
                "schema": {
                    **_JOB_MULTIPART_SCHEMA,
                    "required": [],
                },
            },
        },
    },
}


def _parse_skills_form_value(values: list[Any]) -> list[str] | None:
    text_values = [str(value).strip() for value in values if not isinstance(value, StarletteUploadFile)]
    text_values = [value for value in text_values if value]
    if not text_values:
        return None

    if len(text_values) == 1:
        raw = text_values[0]
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        if "," in raw:
            return [item.strip() for item in raw.split(",") if item.strip()]

    return text_values


def _parse_list_form_value(values: list[Any]) -> list[str] | None:
    text_values = [str(value).strip() for value in values if not isinstance(value, StarletteUploadFile)]
    text_values = [value for value in text_values if value]
    if not text_values:
        return None

    if len(text_values) == 1:
        raw = text_values[0]
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        if "," in raw:
            return [item.strip() for item in raw.split(",") if item.strip()]

    return text_values


async def _read_job_request_data(http_request: Request) -> tuple[dict[str, Any], StarletteUploadFile | None]:
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        data: dict[str, Any] = {}
        for field in _JOB_FORM_FIELDS:
            value = form.get(field)
            if value is not None and not isinstance(value, StarletteUploadFile):
                data[field] = value

        skills = _parse_skills_form_value(form.getlist("skills"))
        if skills is not None:
            data["skills"] = skills

        for field in _JOB_LIST_FORM_FIELDS:
            values = _parse_list_form_value(form.getlist(field))
            if values is not None:
                data[field] = values

        document = form.get("job_description_document")
        if isinstance(document, StarletteUploadFile):
            return data, document
        return data, None

    try:
        payload = await http_request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be an object")
    return payload, None


async def _apply_job_description_document(
    data: dict[str, Any],
    document: StarletteUploadFile | None,
) -> None:
    if document is None:
        return

    if str(data.get("job_description") or "").strip():
        return

    contents = await document.read()
    extracted_text = DocumentTextExtractionService.extract_text_from_upload(
        filename=document.filename,
        content_type=document.content_type,
        contents=contents,
    )
    data["job_description"] = extracted_text
    logger.info(
        "Populated job description from uploaded document.",
        extra={"filename": document.filename},
    )


def _build_post_job_request(data: dict[str, Any]) -> PostJobRequestSchema:
    try:
        return PostJobRequestSchema(**data)
    except ValidationError as exc:
        _raise_clear_job_description_error(exc)
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _build_update_job_request(data: dict[str, Any]) -> UpdateJobRequestSchema:
    try:
        return UpdateJobRequestSchema(**data)
    except ValidationError as exc:
        _raise_clear_job_description_error(exc)
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _raise_clear_job_description_error(exc: ValidationError) -> None:
    for error in exc.errors():
        loc = error.get("loc") or ()
        if "job_description" in loc and error.get("type") == "string_too_long":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Job description must not exceed "
                    f"{MAX_JOB_DESCRIPTION_LENGTH} characters. "
                    "Please upload a smaller file or shorten the description."
                ),
            ) from exc



async def _get_or_create_employer_profile(
    session: AsyncSession,
    payload: dict,
    company_name: Optional[str] = None,
) -> EmployerProfile:
    query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
    result = await session.execute(query)
    employer = result.scalar_one_or_none()
    if employer:
        return employer

    employer = EmployerProfile(
        id=str(uuid4()),
        user_id=payload.get("user_id"),
        company_name=company_name or "Unknown Company",
        created_by=str(payload.get("user_id")) if payload.get("user_id") else None,
        updated_by=str(payload.get("user_id")) if payload.get("user_id") else None,
    )
    session.add(employer)

    try:
        await commit_rollback(session)
    except IntegrityError:
        await session.rollback()
        result = await session.execute(query)
        employer = result.scalar_one_or_none()
        if employer:
            return employer
        raise HTTPException(status_code=403, detail="Employer profile not found")

    return employer


@router.post(
    "/ai/generate-description",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Generate a job description with AI",
)
async def generate_job_description_with_ai(
    request_body: AIJobDescriptionGenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
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
    "/ai/improve-description",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Improve a job description with AI",
)
async def improve_job_description_with_ai(
    request_body: AIJobDescriptionImproveRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
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
    "/ai/regenerate",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Regenerate one job description section with AI",
)
async def regenerate_job_description_section_with_ai(
    request_body: AIJobDescriptionRegenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
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
    "/ai/generate-description/stream",
    summary="Stream a generated job description with server-sent events",
)
async def stream_job_description_with_ai(
    request_body: AIJobDescriptionGenerateRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    employer = await _get_existing_employer_profile(session=session, payload=payload)
    return StreamingResponse(
        AIJobDescriptionService.stream_generate_description(
            session=session,
            payload=payload,
            employer=employer,
            request=request_body,
        ),
        media_type="text/event-stream",
    )


@router.get(
    "/list",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="My jobs list",
    description="List jobs for the authenticated employer (based on JWT payload).",
)
async def list_jobs(
    search: str = "",
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    experience: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[
        Literal[
            "POSTED_DATE_DESC",
            "POSTED_DATE_ASC",
            "JOB_TITLE_ASC",
            "JOB_TITLE_DESC",
            "LOCATION_ASC",
            "LOCATION_DESC",
        ]
    ] = None,
    page: int = 1,
    page_size: int = 20,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
    clear_filters: bool = False,
):
    filters = JobListFiltersSchema(
        search=search if not clear_filters else "",
        location=location,
        employment_type=employment_type,
        experience=experience,
        status=status,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
        clear_filters=clear_filters,
    )



    result = await JobService.list_employer_jobs(
        session=session,
        payload=payload,
        filters=filters,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Jobs fetched successfully",
        data=result,
    )
   


@router.get("/{job_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Get job details")
async def get_job_details(
    job_id: str,

    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    
    result = None
    if _use_legacy_db_proxy():
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == payload.get("user_id")
            )
        )
    if result is None:
        query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
        result = await session.execute(query)

    employer = result.scalar_one_or_none()

    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")

    job = await JobService.get_job_for_employer(
        session=session,
        employer_id=str(employer.id),
        job_id=job_id,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Job fetched successfully",
        data=PostJobResponseSchema.model_validate(job).model_dump(),
    )



@router.put(
    "/{job_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    openapi_extra=_PUT_JOB_OPENAPI_EXTRA,
)
async def put_job(
    job_id: str,
    http_request: Request,


    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    request_data, document = await _read_job_request_data(http_request)
    await _apply_job_description_document(request_data, document)
    request_body = _build_update_job_request(request_data)

    
    result = None
    if _use_legacy_db_proxy():
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == payload.get("user_id")
            )
        )

    if result is None:
        query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
        result = await session.execute(query)

    employer = result.scalar_one_or_none()

    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")

    job = await JobService.update_job(

        session=session,
        employer_id=str(employer.id),
        job_id=job_id,
        request=request_body,
        actor_user_id=str(payload.get("user_id")) if payload.get("user_id") else None,
        actor_email=payload.get("email"),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Job updated successfully",
        data=PostJobResponseSchema.model_validate(job).model_dump(),
    )


@employer_router.patch(
    "/{job_id}/reopen",

    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Reopen closed job",
    tags=["My Jobs"],

    responses={
        200: {"description": "Job reopened successfully"},
        400: {"description": "Only closed jobs can be reopened."},
        403: {"description": "Forbidden"},
        404: {"description": "Job not found"},
        500: {"description": "Internal Server Error"},
    },
)
async def reopen_job(
    job_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = None
    if _use_legacy_db_proxy():
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == payload.get("user_id")
            )
        )

    if result is None:
        query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
        result = await session.execute(query)

    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")

    job = await JobService.reopen_job(
        session=session,
        employer_id=str(employer.id),
        job_id=job_id,
        actor_user_id=str(payload.get("user_id")) if payload.get("user_id") else None,
        actor_email=payload.get("email"),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Job reopened successfully.",
        data=ReopenJobResponseData(
            job_id=job.job_id,
            status=job.status,
        ).model_dump(),
    )





@employer_router.patch("/{job_id}/close", response_model=ResponseSchema, response_model_exclude_none=True)
async def close_job(
    job_id: str,
    request_body: CloseJobRequest,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):

    result = None
    if _use_legacy_db_proxy():
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == payload.get("user_id")
            )
        )

    if result is None:
        query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
        result = await session.execute(query)

    employer = result.scalar_one_or_none()

    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")

    job = await JobService.close_job(
        session=session,
        employer_id=str(employer.id),
        job_id=job_id,
        request=request_body,
        actor_user_id=str(payload.get("user_id")) if payload.get("user_id") else None,
        actor_email=payload.get("email"),
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Job closed successfully.",
        data=CloseJobResponse(
            job_id=job.job_id,
            status=job.status,
            closed_at=job.closed_at,
            closed_reason=job.closed_reason,
        ).model_dump(),
    )


@employer_router.delete("/{job_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def delete_job(
    job_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    result = None
    if _use_legacy_db_proxy():
        result = await db.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == payload.get("user_id")
            )
        )

    if result is None:
        query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
        result = await session.execute(query)

    employer = result.scalar_one_or_none()

    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")

    result = await delete_job_service(
        job_id=job_id,
        current_user=payload,
        db=session,
        employer_id=str(employer.id),
    )

    return ResponseSchema(
        success=result["success"],
        status=200,
        message=result["message"],
    )


@router.post(
    "/",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
    openapi_extra=_POST_JOB_OPENAPI_EXTRA,
)
async def post_job(
    http_request: Request,
    idempotency_key: Optional[str] = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
    request_id: Optional[str] = Header(
        default=None,
        convert_underscores=False,
        alias="X-Request-ID",
    ),
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    request_data, document = await _read_job_request_data(http_request)
    await _apply_job_description_document(request_data, document)
    request_body = _build_post_job_request(request_data)

    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if idempotency_key == "":
            raise HTTPException(status_code=400, detail="Idempotency-Key cannot be empty")

    employer = await _get_or_create_employer_profile(
        session=session,
        payload=payload,
        company_name=request_body.company_name,
    )

    job = await JobService.create_post_job(
        session=session,
        payload=payload,
        employer_id=str(employer.id),
        request=request_body,
        idempotency_key=idempotency_key,
        request_id=request_id,
    )

    return created_response(
        message="Job created successfully",
        data=PostJobResponseSchema.model_validate(job).model_dump(),
    )
