import logging
import mimetypes
from pathlib import Path
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.schema.common import ResponseSchema
from app.candidate_schema import (
    CandidateListingFilterParams,
    ExperienceLevel,
    WorkPreference,
    CandidatePersonalInfoUpdateSchema,
    CandidateSocialLinksUpdateSchema,
    CandidateSkillCreateSchema,
    CandidateSkillUpdateSchema,
    CandidateEducationCreateSchema,
    CandidateEducationUpdateSchema,
    CandidateExperienceCreateSchema,
    CandidateExperienceUpdateSchema,
    CandidateCertificationsUpdateSchema,
    CandidateCertificationUpdateSchema,
    CertificationEntrySchema,
    CandidateProjectCreateSchema,
    CandidateProjectUpdateSchema,
    CandidateLanguageCreateSchema,
    CandidateLanguageUpdateSchema,
    CandidateVisibilityUpdateSchema,
    CandidateProfessionalSnapshotUpdateSchema,
    CandidateSavedJobCreateSchema,
    JobAlertUpsertSchema,
    JobAlertUpdateSchema,
    SavedSearchCreateSchema,
    CandidateResumeUpdateSchema,
    ResumeShareLinkCreateSchema,
    SharedResumeAccessRequestSchema,
    ExtractedResumeDataSchema,
    ResumeStudioDraftSchema,
)
from app.service.candidate_service import CandidateProfileService
from app.service.candidate_dashboard_service import CandidateDashboardService

router = APIRouter(
    prefix="/candidate",
    tags=["Candidate Profile"],
)
logger = logging.getLogger(__name__)

public_router = APIRouter(
    prefix="/candidates",
    tags=["Candidate Listing"],
)


def _get_user_id(payload: dict = Depends(get_jwt_payload_401)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


def _file_response_for_resume(payload: dict) -> FileResponse:
    file_path = payload.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="Resume file not found")

    path = Path(file_path).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Resume file not found")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    filename = payload.get("file_name") or path.name
    return FileResponse(path=path, filename=filename, media_type=media_type)


# ---------------------------------------------------------------------------
# Public candidate listing
# ---------------------------------------------------------------------------

@public_router.get("", response_model=ResponseSchema, response_model_exclude_none=True, summary="Candidate listing")
async def list_candidates(
    search: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=100),
    skill: str | None = Query(default=None, max_length=100),
    experience_level: ExperienceLevel | None = Query(default=None),
    work_preference: WorkPreference | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    filters = CandidateListingFilterParams(
        search=search,
        location=location,
        skill=skill,
        experience_level=experience_level,
        work_preference=work_preference,
        page=page,
        page_size=page_size,
    )
    result = await CandidateProfileService.list_public_candidates(session, filters)
    return ResponseSchema(
        success=True,
        status=200,
        message="Candidates fetched successfully",
        data=result.model_dump()
    )


@public_router.get("/{candidate_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Candidate detail")
async def get_candidate_detail(candidate_id: str, session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_public_candidate_detail(session, candidate_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Candidates fetched successfully",
        data=result.model_dump()
    )


# ---------------------------------------------------------------------------
# Dashboard & profile
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=ResponseSchema, response_model_exclude_none=True, summary="Candidate dashboard", dependencies=[Depends(get_jwt_payload_401)])
async def get_candidate_dashboard(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateDashboardService.get_dashboard(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate dashboard fetched successfully",
        data=result.model_dump()
    )


@router.get("/profile", response_model=ResponseSchema, response_model_exclude_none=True, summary="Get full candidate profile", dependencies=[Depends(get_jwt_payload_401)])
async def get_candidate_profile(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_full_profile(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Candidate profile fetched successfully",
        data=result.model_dump()
    )


@router.patch("/profile/personal-info", response_model=ResponseSchema, response_model_exclude_none=True, summary="Update personal info (partial)", dependencies=[Depends(get_jwt_payload_401)])
async def update_personal_info(body: CandidatePersonalInfoUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_personal_info(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/social-links", response_model=ResponseSchema, response_model_exclude_none=True, summary="Update social links", dependencies=[Depends(get_jwt_payload_401)])
async def update_social_links(body: CandidateSocialLinksUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_social_links(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@router.post("/profile/skills", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add a skill", dependencies=[Depends(get_jwt_payload_401)])
async def add_skill(body: CandidateSkillCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_skill(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/skills/{skill_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit a skill", dependencies=[Depends(get_jwt_payload_401)])
async def update_skill(skill_id: str, body: CandidateSkillUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_skill(session, user_id, skill_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/skills/{skill_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete a skill", dependencies=[Depends(get_jwt_payload_401)])
async def delete_skill(skill_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_skill(session, user_id, skill_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

@router.post("/profile/education", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add an education entry", dependencies=[Depends(get_jwt_payload_401)])
async def add_education(body: CandidateEducationCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_education(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/education/{education_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit an education entry", dependencies=[Depends(get_jwt_payload_401)])
async def update_education(education_id: str, body: CandidateEducationUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_education(session, user_id, education_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/education/{education_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete an education entry", dependencies=[Depends(get_jwt_payload_401)])
async def delete_education(education_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_education(session, user_id, education_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

@router.post("/profile/experience", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add a work experience entry", dependencies=[Depends(get_jwt_payload_401)])
async def add_experience(body: CandidateExperienceCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_experience(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/experience/{experience_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit a work experience entry", dependencies=[Depends(get_jwt_payload_401)])
async def update_experience(experience_id: str, body: CandidateExperienceUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_experience(session, user_id, experience_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/experience/{experience_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete a work experience entry", dependencies=[Depends(get_jwt_payload_401)])
async def delete_experience(experience_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_experience(session, user_id, experience_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Certifications, projects, visibility, professional snapshot
# ---------------------------------------------------------------------------

@router.put("/profile/certifications", response_model=ResponseSchema, response_model_exclude_none=True, summary="Update certifications", dependencies=[Depends(get_jwt_payload_401)])
async def update_certifications(body: CandidateCertificationsUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_certifications(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.post("/profile/certifications", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add a certification", dependencies=[Depends(get_jwt_payload_401)])
async def add_certification(body: CertificationEntrySchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_certification(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/certifications/{certification_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit a certification", dependencies=[Depends(get_jwt_payload_401)])
async def update_certification(certification_id: str, body: CandidateCertificationUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_certification(session, user_id, certification_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/certifications/{certification_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete a certification", dependencies=[Depends(get_jwt_payload_401)])
async def delete_certification(certification_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_certification(session, user_id, certification_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.post("/profile/projects", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add a project", dependencies=[Depends(get_jwt_payload_401)])
async def add_project(body: CandidateProjectCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_project(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/projects/{project_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit a project", dependencies=[Depends(get_jwt_payload_401)])
async def update_project(project_id: str, body: CandidateProjectUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_project(session, user_id, project_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/projects/{project_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete a project", dependencies=[Depends(get_jwt_payload_401)])
async def delete_project(project_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_project(session, user_id, project_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

@router.post("/profile/languages", response_model=ResponseSchema, response_model_exclude_none=True, summary="Add a language", dependencies=[Depends(get_jwt_payload_401)])
async def add_language(body: CandidateLanguageCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.add_language(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/languages/{language_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Edit a language", dependencies=[Depends(get_jwt_payload_401)])
async def update_language(language_id: str, body: CandidateLanguageUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_language(session, user_id, language_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/languages/{language_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete a language", dependencies=[Depends(get_jwt_payload_401)])
async def delete_language(language_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_language(session, user_id, language_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/visibility", response_model=ResponseSchema, response_model_exclude_none=True, summary="Update profile visibility settings", dependencies=[Depends(get_jwt_payload_401)])
async def update_visibility(body: CandidateVisibilityUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_visibility(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.patch("/profile/professional-snapshot", response_model=ResponseSchema, response_model_exclude_none=True, summary="Update professional snapshot (career details)", dependencies=[Depends(get_jwt_payload_401)])
async def update_professional_snapshot(body: CandidateProfessionalSnapshotUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_professional_snapshot(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

@router.post("/profile/resume/upload", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201, summary="Upload resume file", dependencies=[Depends(get_jwt_payload_401)])
async def upload_resume(file: UploadFile = File(...), user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    ALLOWED_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF and Word documents are allowed")

    contents = await file.read()
    resume = await CandidateProfileService.upload_resume_file(
        session=session,
        user_id=user_id,
        filename=file.filename,
        content_type=file.content_type,
        contents=contents,
    )
    return ResponseSchema(
        success=True,
        status=200,
        message="Resume uploaded successfully",
        data=resume.model_dump()
    )


@router.get("/profile/resumes", response_model=ResponseSchema, response_model_exclude_none=True, summary="List uploaded resumes", dependencies=[Depends(get_jwt_payload_401)])
async def list_resumes(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.list_resumes(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Resumes fetched successfully",
        data=result.model_dump()
    )


@router.get("/profile/resume/download", response_model=ResponseSchema, response_model_exclude_none=True, summary="Download active resume file", dependencies=[Depends(get_jwt_payload_401)])
async def download_active_resume(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_resume_download(session, user_id)
    payload = result.model_dump()
    presigned_url = payload.get("file_path")
    if not presigned_url:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return ResponseSchema(success=True, status=200, message="Resume download URL generated", data={"url": presigned_url})


@router.get("/profile/resumes/{resume_id}/download", response_model=ResponseSchema, response_model_exclude_none=True, summary="Download resume file", dependencies=[Depends(get_jwt_payload_401)])
async def download_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_resume_download(session, user_id, resume_id)
    payload = result.model_dump()
    presigned_url = payload.get("file_path")
    if not presigned_url:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return ResponseSchema(success=True, status=200, message="Resume download URL generated", data={"url": presigned_url})


@router.get("/profile/resume/download-file", summary="Download the active resume's raw file bytes", dependencies=[Depends(get_jwt_payload_401)])
async def download_active_resume_file(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    content, filename, content_type = await CandidateProfileService.get_resume_download_file(session, user_id)
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/profile/resumes/{resume_id}/download-file", summary="Download a specific resume version's raw file bytes", dependencies=[Depends(get_jwt_payload_401)])
async def download_resume_file(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    content, filename, content_type = await CandidateProfileService.get_resume_download_file(session, user_id, resume_id)
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/profile/resume/preview-file", summary="Fetch the active resume's raw file bytes for inline preview (not counted as a download)", dependencies=[Depends(get_jwt_payload_401)])
async def preview_active_resume_file(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    content, filename, content_type = await CandidateProfileService.get_resume_download_file(
        session, user_id, count_as_download=False
    )
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/profile/resumes/{resume_id}/preview-file", summary="Fetch a specific resume version's raw file bytes for inline preview (not counted as a download)", dependencies=[Depends(get_jwt_payload_401)])
async def preview_resume_file(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    content, filename, content_type = await CandidateProfileService.get_resume_download_file(
        session, user_id, resume_id, count_as_download=False
    )
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/profile/resume/preview", response_model=ResponseSchema, response_model_exclude_none=True, summary="Preview the candidate's default resume", dependencies=[Depends(get_jwt_payload_401)])
async def preview_active_resume(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_resume_preview(session, user_id)
    payload = result.model_dump()
    presigned_url = payload.get("file_path")
    if not presigned_url:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return ResponseSchema(
        success=True,
        status=200,
        message="Resume preview URL generated",
        data={"url": presigned_url, "resume_id": payload.get("resume_id")},
    )


@router.get("/profile/resumes/{resume_id}/preview", response_model=ResponseSchema, response_model_exclude_none=True, summary="Preview a specific resume version", dependencies=[Depends(get_jwt_payload_401)])
async def preview_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_resume_preview(session, user_id, resume_id)
    payload = result.model_dump()
    presigned_url = payload.get("file_path")
    if not presigned_url:
        raise HTTPException(status_code=404, detail="Resume file not found")
    return ResponseSchema(
        success=True,
        status=200,
        message="Resume preview URL generated",
        data={"url": presigned_url, "resume_id": payload.get("resume_id")},
    )


@router.get(
    "/profile/resumes/{resume_id}/parse",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Parse an uploaded resume file into structured data (heuristic, best-effort)",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def parse_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    data = await CandidateProfileService.parse_resume_content(session, user_id, resume_id)
    return ResponseSchema(success=True, status=200, message="Resume parsed", data=ExtractedResumeDataSchema(**data).model_dump())


@router.get("/profile/resume/generate", summary="Generate a resume PDF on the fly (ATS, Sidebar, or Bold Header template, each optionally in the Modern Visual typography variant)", dependencies=[Depends(get_jwt_payload_401)])
async def generate_resume_pdf(
    style: str = Query(
        default="ats",
        pattern="^(ats|modern|ats-modern|sidebar|sidebar-modern|bold-header|bold-header-modern)$",
    ),
    resume_id: Optional[str] = Query(default=None),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await CandidateProfileService.generate_resume_pdf(session, user_id, style=style, resume_id=resume_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/profile/resume-studio/generate",
    summary="Render a Resume Studio draft (never persisted) into a PDF using the same templates as Download CV",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def generate_resume_studio_pdf(
    payload: ResumeStudioDraftSchema,
    style: str = Query(default="ats", pattern="^(ats|sidebar|bold-header)$"),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await CandidateProfileService.generate_resume_studio_pdf(
        session, user_id, payload.model_dump(), style=style
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/profile/photo/upload", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201, summary="Upload profile picture", dependencies=[Depends(get_jwt_payload_401)])
async def upload_profile_picture(file: UploadFile = File(...), user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    contents = await file.read()
    result = await CandidateProfileService.upload_profile_picture(
        session=session,
        user_id=user_id,
        filename=file.filename,
        content_type=file.content_type,
        contents=contents,
    )
    return ResponseSchema(
        success=True,
        status=201,
        message=result["message"],
        data={"url": result["url"]},
    )


@router.delete("/profile/photo", response_model=ResponseSchema, response_model_exclude_none=True, status_code=200, summary="Remove profile picture", dependencies=[Depends(get_jwt_payload_401)])
async def remove_profile_picture(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.remove_profile_picture(session=session, user_id=user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
    )


@router.post("/profile/cover/upload", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201, summary="Upload cover picture", dependencies=[Depends(get_jwt_payload_401)])
async def upload_cover_picture(file: UploadFile = File(...), user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    contents = await file.read()
    result = await CandidateProfileService.upload_cover_picture(
        session=session,
        user_id=user_id,
        filename=file.filename,
        content_type=file.content_type,
        contents=contents,
    )
    return ResponseSchema(
        success=True,
        status=201,
        message=result["message"],
        data={"url": result["url"]},
    )


@router.patch("/profile/resumes/{resume_id}/active", response_model=ResponseSchema, response_model_exclude_none=True, summary="Set active resume", dependencies=[Depends(get_jwt_payload_401)])
async def set_active_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.set_active_resume(session, user_id, resume_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/profile/resumes/{resume_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete uploaded resume", dependencies=[Depends(get_jwt_payload_401)])
async def delete_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_resume(session, user_id, resume_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=None
    )


@router.patch("/profile/resumes/{resume_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Rename / re-template / annotate a resume version", dependencies=[Depends(get_jwt_payload_401)])
async def update_resume(resume_id: str, payload: CandidateResumeUpdateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.update_resume(session, user_id, resume_id, payload)
    return ResponseSchema(success=True, status=200, message="Resume updated successfully", data=result.model_dump())


@router.patch("/profile/resumes/{resume_id}/archive", response_model=ResponseSchema, response_model_exclude_none=True, summary="Archive a resume version", dependencies=[Depends(get_jwt_payload_401)])
async def archive_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.set_resume_archived(session, user_id, resume_id, archived=True)
    return ResponseSchema(success=True, status=200, message="Resume archived successfully", data=result.model_dump())


@router.patch("/profile/resumes/{resume_id}/restore", response_model=ResponseSchema, response_model_exclude_none=True, summary="Restore an archived resume version", dependencies=[Depends(get_jwt_payload_401)])
async def restore_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.set_resume_archived(session, user_id, resume_id, archived=False)
    return ResponseSchema(success=True, status=200, message="Resume restored successfully", data=result.model_dump())


@router.post("/profile/resumes/{resume_id}/duplicate", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201, summary="Duplicate a resume version", dependencies=[Depends(get_jwt_payload_401)])
async def duplicate_resume(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.duplicate_resume(session, user_id, resume_id)
    return ResponseSchema(success=True, status=201, message="Resume duplicated successfully", data=result.model_dump())


@router.post("/profile/resumes/{resume_id}/share", response_model=ResponseSchema, response_model_exclude_none=True, summary="Create or refresh a resume share link", dependencies=[Depends(get_jwt_payload_401)])
async def create_resume_share_link(resume_id: str, payload: ResumeShareLinkCreateSchema = ResumeShareLinkCreateSchema(), user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.create_resume_share_link(session, user_id, resume_id, payload)
    return ResponseSchema(success=True, status=200, message="Share link created successfully", data=result.model_dump())


@router.patch("/profile/resumes/{resume_id}/share/disable", response_model=ResponseSchema, response_model_exclude_none=True, summary="Disable a resume share link", dependencies=[Depends(get_jwt_payload_401)])
async def disable_resume_share_link(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.disable_resume_share_link(session, user_id, resume_id)
    return ResponseSchema(success=True, status=200, message="Share link disabled successfully", data=result.model_dump())


@router.patch("/profile/resumes/{resume_id}/share/enable", response_model=ResponseSchema, response_model_exclude_none=True, summary="Re-enable a previously disabled resume share link", dependencies=[Depends(get_jwt_payload_401)])
async def enable_resume_share_link(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.enable_resume_share_link(session, user_id, resume_id)
    return ResponseSchema(success=True, status=200, message="Share link enabled successfully", data=result.model_dump())


@router.delete("/profile/resumes/{resume_id}/share", response_model=ResponseSchema, response_model_exclude_none=True, summary="Permanently delete a resume share link", dependencies=[Depends(get_jwt_payload_401)])
async def delete_resume_share_link(resume_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_resume_share_link(session, user_id, resume_id)
    return ResponseSchema(success=True, status=200, message="Share link deleted successfully", data=result.model_dump())


# ---------------------------------------------------------------------------
# Public share link resolution -- backs the /cv/{token} page. Intentionally
# NOT behind get_jwt_payload_401: anyone holding the link should be able to
# view/download the shared resume, same as a real "share link" product.
# ---------------------------------------------------------------------------

@router.get("/public/resume/{share_token}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Resolve a shared resume link")
async def get_shared_resume_info(share_token: str, session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.get_shared_resume_info(session, share_token)
    return ResponseSchema(success=True, status=200, message="Shared resume fetched successfully", data=result.model_dump())


@router.post("/public/resume/{share_token}/access", response_model=ResponseSchema, response_model_exclude_none=True, summary="Unlock an email-gated shared resume link")
async def access_shared_resume(share_token: str, payload: SharedResumeAccessRequestSchema, session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.access_shared_resume(session, share_token, payload.email)
    return ResponseSchema(success=True, status=200, message="Resume unlocked successfully", data=result.model_dump())


# ---------------------------------------------------------------------------
# Saved jobs & job alerts
# ---------------------------------------------------------------------------

@router.get("/saved-jobs", response_model=ResponseSchema, response_model_exclude_none=True, summary="List saved jobs", dependencies=[Depends(get_jwt_payload_401)])
async def list_saved_jobs(page: int = 1, page_size: int = 20, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.list_saved_jobs(session, user_id, page, page_size)
    return ResponseSchema(
        success=True,
        status=200,
        message="Saved jobs fetched successfully",
        data=result.model_dump()
    )


@router.get("/favourite-jobs", response_model=ResponseSchema, response_model_exclude_none=True, summary="Template alias for saved jobs", dependencies=[Depends(get_jwt_payload_401)])
async def list_favourite_jobs(page: int = 1, page_size: int = 20, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.list_saved_jobs(session, user_id, page, page_size)
    return ResponseSchema(
        success=True,
        status=200,
        message="Favourite jobs fetched successfully",
        data=result.model_dump()
    )


@router.post("/saved-jobs", response_model=ResponseSchema, response_model_exclude_none=True, summary="Save a job", dependencies=[Depends(get_jwt_payload_401)])
async def save_job(body: CandidateSavedJobCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.save_job(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=result
    )


@router.delete("/saved-jobs/{job_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Remove saved job", dependencies=[Depends(get_jwt_payload_401)])
async def unsave_job(job_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.unsave_job(session, user_id, job_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=None
    )


@router.get("/job-alerts", response_model=ResponseSchema, response_model_exclude_none=True, summary="List job alerts", dependencies=[Depends(get_jwt_payload_401)])
async def list_job_alerts(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.list_job_alerts(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Job alerts fetched successfully",
        data=[item.model_dump() for item in result]
    )


@router.post(
    "/job-alerts",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Create job alert",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def create_job_alert(
    body: JobAlertUpsertSchema,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        result = await CandidateProfileService.create_job_alert(
            session,
            user_id,
            body,
        )

        return ResponseSchema(
            success=True,
            status=200,
            message="Job alert created successfully",
            data=result.model_dump(),
        )

    except Exception:
        logger.exception("Failed to create candidate job alert.")
        raise


@router.put(
    "/job-alerts/{alert_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    summary="Update job alert",
    dependencies=[Depends(get_jwt_payload_401)],
)
async def update_job_alert(
    alert_id: str,
    body: JobAlertUpdateSchema,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await CandidateProfileService.update_job_alert(
        session,
        user_id,
        alert_id,
        body,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Job alert updated successfully",
        data=result.model_dump(),
    )

@router.delete("/job-alerts/{alert_id}", response_model=ResponseSchema, response_model_exclude_none=True, summary="Delete job alert", dependencies=[Depends(get_jwt_payload_401)])
async def delete_job_alert(alert_id: str, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.delete_job_alert(session, user_id, alert_id)
    return ResponseSchema(
        success=True,
        status=200,
        message=result["message"],
        data=None
    )


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------

@router.get("/saved-searches", response_model=ResponseSchema, response_model_exclude_none=True, summary="List saved searches", dependencies=[Depends(get_jwt_payload_401)])
async def list_saved_searches(user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.list_saved_searches(session, user_id)
    return ResponseSchema(
        success=True,
        status=200,
        message="Saved searches fetched successfully",
        data=[item.model_dump() for item in result]
    )


@router.post("/saved-searches", response_model=ResponseSchema, response_model_exclude_none=True, summary="Create saved search", dependencies=[Depends(get_jwt_payload_401)])
async def create_saved_search(body: SavedSearchCreateSchema, user_id: UUID = Depends(_get_user_id), session: AsyncSession = Depends(get_db)):
    result = await CandidateProfileService.create_saved_search(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=200,
        message="Saved search created successfully",
        data=result.model_dump()
    )
