from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.repository.profile_repo import CompanyProfileRepository, EmployerProfileRepository
from app.schema.profile import (
    CompanyProfileCreate,
    CompanyProfileResponse,
    CompanyProfileUpdate,
    CompanySearchResponse,
    EmployerDashboardSummary,
    EmployerProfileCreate,
    EmployerProfileResponse,
    EmployerProfileUpdate,
    ProfileCompletionResponse,
    dump_profile_update,
)
from app.service import s3_service
from app.service.super_admin.activity_log_service import ActivityLogService
from app.utils.activity_mapper import build_recent_activity, unpack_activity_row


logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
}
ALLOWED_EXTENSIONS = {
    "jpg": ("image/jpeg", ".jpg"),
    "jpeg": ("image/jpeg", ".jpg"),
    "png": ("image/png", ".png"),
    "svg": ("image/svg+xml", ".svg"),
}


def _user_id_from_payload(payload: dict[str, Any]) -> UUID:
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(user_id))


def _audit_user(payload: dict[str, Any]) -> str:
    return str(_user_id_from_payload(payload))


def _display_s3_url(stored_value: Optional[str]) -> Optional[str]:
    if not stored_value:
        return None
    if stored_value.startswith(("http://", "https://", "/uploads/")):
        return stored_value
    try:
        return s3_service.generate_presigned_url(stored_value, expiry_seconds=3600)
    except Exception:
        logger.warning("Failed to generate presigned URL for S3 key=%s", stored_value)
        return None


def _serialize_company(profile: CompanyProfile) -> CompanyProfileResponse:
    if not profile.logo_url and profile.logo_path:
        profile.logo_url = profile.logo_path
    if not profile.company_size and profile.size:
        profile.company_size = profile.size
    response = CompanyProfileResponse.model_validate(profile)
    data = response.model_dump()
    data["logo_url"] = _display_s3_url(data.get("logo_url"))
    return CompanyProfileResponse(**data)


def _serialize_employer(profile: EmployerProfile) -> EmployerProfileResponse:
    response = EmployerProfileResponse.model_validate(profile)
    data = response.model_dump()
    data["profile_photo"] = _display_s3_url(data.get("profile_photo"))
    return EmployerProfileResponse(**data)


async def _read_valid_image(
    upload: UploadFile,
    allowed_svg: bool = True,
) -> tuple[bytes, str, str]:
    filename = upload.filename or ""
    content_type = upload.content_type or ""
    extension = ALLOWED_IMAGE_TYPES.get(content_type)

    if not extension and "." in filename:
        suffix = filename.rsplit(".", 1)[-1].lower()
        mapped = ALLOWED_EXTENSIONS.get(suffix)
        if mapped:
            content_type, extension = mapped

    if not extension or (extension == ".svg" and not allowed_svg):
        message = (
            "Only JPG, JPEG, PNG, and SVG images are allowed"
            if allowed_svg
            else "Only JPG, JPEG, and PNG images are allowed"
        )
        raise HTTPException(status_code=400, detail=message)

    content = await upload.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File size must not exceed 5 MB")

    return content, extension, content_type


class EmployerProfileService:
    @staticmethod
    async def _get_owned_profile(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> EmployerProfile:
        user_id = _user_id_from_payload(payload)
        profile = await EmployerProfileRepository.get_by_user_id(session, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Employer profile not found")
        return profile

    @staticmethod
    async def create(
        session: AsyncSession,
        payload: dict[str, Any],
        request: EmployerProfileCreate,
    ) -> EmployerProfileResponse:
        user_id = _user_id_from_payload(payload)
        existing = await EmployerProfileRepository.get_by_user_id(session, user_id)
        if existing:
            raise HTTPException(status_code=409, detail="Employer profile already exists")

        data = dump_profile_update(request)
        now = datetime.now(timezone.utc)
        profile = EmployerProfile(
            id=uuid4().hex,
            user_id=user_id,
            company_name=data.pop("company_name", "Unspecified Company"),
            created_at=now,
            updated_at=now,
            created_by=_audit_user(payload),
            updated_by=_audit_user(payload),
            **data,
        )
        try:
            created = await EmployerProfileRepository.create(session, profile)
            await session.commit()
            logger.info("Employer profile created. user_id=%s employer_id=%s", user_id, created.id)
            await ActivityLogService.create_log(
                session=session,
                actor={**payload, "role_code": "ROLE_EMPLOYER"},
                action="EMPLOYER_PROFILE_CREATED",
                entity_type="EmployerProfile",
                entity_id=created.id,
                target_entity_name=created.company_name,
                description="Employer profile created",
            )
            return _serialize_employer(created)
        except Exception:
            await session.rollback()
            logger.exception("Failed to create employer profile. user_id=%s", user_id)
            raise

    @staticmethod
    async def get(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> EmployerProfileResponse:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        return _serialize_employer(profile)

    @staticmethod
    async def update(
        session: AsyncSession,
        payload: dict[str, Any],
        request: EmployerProfileUpdate,
    ) -> EmployerProfileResponse:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        update_data = dump_profile_update(request)
        for field, value in update_data.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.now(timezone.utc)
        profile.updated_by = _audit_user(payload)
        try:
            saved = await EmployerProfileRepository.save(session, profile)
            await session.commit()
            logger.info("Employer profile updated. user_id=%s employer_id=%s", profile.user_id, profile.id)
            await ActivityLogService.create_log(
                session=session,
                actor={**payload, "role_code": "ROLE_EMPLOYER"},
                action="EMPLOYER_PROFILE_UPDATED",
                entity_type="EmployerProfile",
                entity_id=profile.id,
                target_entity_name=getattr(profile, "company_name", None),
                description="Employer profile updated",
            )
            return _serialize_employer(saved)
        except Exception:
            await session.rollback()
            logger.exception("Failed to update employer profile. employer_id=%s", profile.id)
            raise

    @staticmethod
    async def upload_photo(
        session: AsyncSession,
        payload: dict[str, Any],
        upload: UploadFile,
    ) -> EmployerProfileResponse:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        contents, extension, content_type = await _read_valid_image(upload, allowed_svg=False)
        if profile.profile_photo:
            try:
                s3_service.delete_object(profile.profile_photo)
            except Exception:
                logger.warning("Failed to delete previous employer profile photo. employer_id=%s", profile.id)
        profile.profile_photo = s3_service.upload_employer_profile_photo(
            contents=contents,
            employer_id=profile.id,
            extension=extension,
            content_type=content_type,
        )
        profile.updated_at = datetime.now(timezone.utc)
        profile.updated_by = _audit_user(payload)
        await EmployerProfileRepository.save(session, profile)
        await session.commit()
        await ActivityLogService.create_log(
            session=session,
            actor={**payload, "role_code": "ROLE_EMPLOYER"},
            action="EMPLOYER_PROFILE_UPDATED",
            entity_type="EmployerProfile",
            entity_id=profile.id,
            target_entity_name=getattr(profile, "company_name", None),
            description="Employer profile photo uploaded",
        )
        return _serialize_employer(profile)

    @staticmethod
    async def delete_photo(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> EmployerProfileResponse:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        if profile.profile_photo:
            try:
                s3_service.delete_object(profile.profile_photo)
            except Exception:
                logger.warning("Failed to delete employer profile photo from S3. employer_id=%s", profile.id)
        profile.profile_photo = None
        profile.updated_at = datetime.now(timezone.utc)
        profile.updated_by = _audit_user(payload)
        await EmployerProfileRepository.save(session, profile)
        await session.commit()
        await ActivityLogService.create_log(
            session=session,
            actor={**payload, "role_code": "ROLE_EMPLOYER"},
            action="EMPLOYER_PROFILE_UPDATED",
            entity_type="EmployerProfile",
            entity_id=profile.id,
            target_entity_name=getattr(profile, "company_name", None),
            description="Employer profile photo deleted",
        )
        return _serialize_employer(profile)

    @staticmethod
    def calculate_profile_completion(profile: EmployerProfile) -> ProfileCompletionResponse:
        checks = {
            "profile_photo": profile.profile_photo,
            "bio": profile.bio,
            "job_title": profile.job_title,
            "department": profile.department,
            "experience_years": profile.experience_years is not None,
            "languages": profile.languages,
            "linkedin_url": profile.linkedin_url,
            "website_url": profile.website_url,
            "specializations": any(
                [
                    profile.specialization_1,
                    profile.specialization_2,
                    profile.specialization_3,
                    profile.specialization_4,
                ]
            ),
            "location": profile.location,
        }
        missing = [field for field, value in checks.items() if not value]
        completed = len(checks) - len(missing)
        percentage = int(round((completed / len(checks)) * 100))
        return ProfileCompletionResponse(
            completion_percentage=percentage,
            missing_fields=missing,
        )

    @staticmethod
    async def completion(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> ProfileCompletionResponse:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        return EmployerProfileService.calculate_profile_completion(profile)

    @staticmethod
    async def dashboard(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> EmployerDashboardSummary:
        profile = await EmployerProfileService._get_owned_profile(session, payload)
        completion = EmployerProfileService.calculate_profile_completion(profile)
        responded, total = await EmployerProfileRepository.count_responded_applications(
            session,
            profile.id,
        )
        response_rate = int(round((responded / total) * 100)) if total else 0
        active_jobs = await EmployerProfileRepository.fetch_active_jobs(session, profile.id)
        recent_activity = await EmployerProfileRepository.fetch_recent_activity(session, profile.id)
        return EmployerDashboardSummary(
            profile_completion=completion.completion_percentage,
            candidates_contacted=await EmployerProfileRepository.count_candidates_contacted(session, profile.id),
            response_rate=response_rate,
            interviews_scheduled=await EmployerProfileRepository.count_interviews_scheduled(session, profile.id),
            candidate_rating=await EmployerProfileRepository.average_candidate_rating(session, profile.id),
            active_jobs=[
                {
                    "job_id": job.job_id,
                    "title": job.title,
                    "status": job.status,
                    "location": job.location,
                }
                for job in active_jobs
            ],
            recent_activity=[
                build_recent_activity(
                    activity,
                    job_title=getattr(job, "title", None),
                )
                for activity, job in (unpack_activity_row(row) for row in recent_activity)
            ],
        )


class CompanyProfileService:
    @staticmethod
    async def _get_employer_profile(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> EmployerProfile:
        user_id = _user_id_from_payload(payload)
        employer = await EmployerProfileRepository.get_by_user_id(session, user_id)
        if not employer:
            raise HTTPException(status_code=403, detail="Employer profile not found")
        return employer

    @staticmethod
    async def create(
        session: AsyncSession,
        payload: dict[str, Any],
        request: CompanyProfileCreate,
    ) -> CompanyProfileResponse:
        employer = await CompanyProfileService._get_employer_profile(session, payload)
        existing = await CompanyProfileRepository.get_by_employer_id(session, employer.id)
        if existing:
            raise HTTPException(status_code=409, detail="Company profile already exists")
        data = dump_profile_update(request)
        data["size"] = data.get("company_size")
        data["logo_path"] = data.get("logo_url")
        data["location"] = ", ".join(
            filter(
                None,
                [
                    data.get("headquarters_city"),
                    data.get("headquarters_state"),
                    data.get("headquarters_country"),
                ],
            )
        ) or None
        profile = CompanyProfile(
            employer_id=employer.id,
            created_by=_audit_user(payload),
            updated_by=_audit_user(payload),
            **data,
        )
        try:
            created = await CompanyProfileRepository.create(session, profile)
            await session.commit()
            logger.info("Company profile created. employer_id=%s company_id=%s", employer.id, created.company_id)
            await ActivityLogService.create_log(
                session=session,
                actor={**payload, "role_code": "ROLE_EMPLOYER"},
                action="COMPANY_CREATED",
                entity_type="Company",
                entity_id=created.company_id,
                target_entity_name=created.company_name,
                description=f"Created company {created.company_name}",
            )
            return _serialize_company(created)
        except Exception:
            await session.rollback()
            logger.exception("Failed to create company profile. employer_id=%s", employer.id)
            raise

    @staticmethod
    async def get(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> CompanyProfileResponse:
        employer = await CompanyProfileService._get_employer_profile(session, payload)
        profile = await CompanyProfileRepository.get_by_employer_id(session, employer.id)
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found")
        return _serialize_company(profile)

    @staticmethod
    async def update(
        session: AsyncSession,
        payload: dict[str, Any],
        request: CompanyProfileUpdate,
    ) -> CompanyProfileResponse:
        employer = await CompanyProfileService._get_employer_profile(session, payload)
        profile = await CompanyProfileRepository.get_by_employer_id(session, employer.id)
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found")
        update_data = dump_profile_update(request)
        if "company_size" in update_data:
            update_data["size"] = update_data["company_size"]
        if "logo_url" in update_data:
            update_data["logo_path"] = update_data["logo_url"]
        location_parts = [
            update_data.get("headquarters_city", profile.headquarters_city),
            update_data.get("headquarters_state", profile.headquarters_state),
            update_data.get("headquarters_country", profile.headquarters_country),
        ]
        if any(field in update_data for field in ("headquarters_city", "headquarters_state", "headquarters_country")):
            update_data["location"] = ", ".join(filter(None, location_parts)) or None
        for field, value in update_data.items():
            setattr(profile, field, value)
        profile.updated_at = utc_now_naive()
        profile.updated_by = _audit_user(payload)
        try:
            saved = await CompanyProfileRepository.save(session, profile)
            await session.commit()
            logger.info("Company profile updated. employer_id=%s company_id=%s", employer.id, profile.company_id)
            await ActivityLogService.create_log(
                session=session,
                actor={**payload, "role_code": "ROLE_EMPLOYER"},
                action="COMPANY_UPDATED",
                entity_type="Company",
                entity_id=profile.company_id,
                target_entity_name=getattr(profile, "company_name", None),
                description=f"Updated company {profile.company_name}",
            )
            return _serialize_company(saved)
        except Exception:
            await session.rollback()
            logger.exception("Failed to update company profile. company_id=%s", profile.company_id)
            raise

    @staticmethod
    async def upload_logo(
        session: AsyncSession,
        payload: dict[str, Any],
        upload: UploadFile,
    ) -> CompanyProfileResponse:
        employer = await CompanyProfileService._get_employer_profile(session, payload)
        profile = await CompanyProfileRepository.get_by_employer_id(session, employer.id)
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found")
        contents, extension, content_type = await _read_valid_image(upload)
        current_logo = profile.logo_url or profile.logo_path
        if current_logo:
            try:
                s3_service.delete_object(current_logo)
            except Exception:
                logger.warning("Failed to delete previous company logo. company_id=%s", profile.company_id)
        s3_key = s3_service.upload_company_logo(
            contents=contents,
            company_id=profile.company_id,
            extension=extension,
            content_type=content_type,
        )
        profile.logo_url = s3_key
        profile.logo_path = s3_key
        profile.updated_at = utc_now_naive()
        profile.updated_by = _audit_user(payload)
        await CompanyProfileRepository.save(session, profile)
        await session.commit()
        await ActivityLogService.create_log(
            session=session,
            actor={**payload, "role_code": "ROLE_EMPLOYER"},
            action="COMPANY_UPDATED",
            entity_type="Company",
            entity_id=profile.company_id,
            target_entity_name=getattr(profile, "company_name", None),
            description=f"Uploaded company logo for {profile.company_name}",
        )
        return _serialize_company(profile)

    @staticmethod
    async def delete_logo(
        session: AsyncSession,
        payload: dict[str, Any],
    ) -> CompanyProfileResponse:
        employer = await CompanyProfileService._get_employer_profile(session, payload)
        profile = await CompanyProfileRepository.get_by_employer_id(session, employer.id)
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found")
        current_logo = profile.logo_url or profile.logo_path
        if current_logo:
            try:
                s3_service.delete_object(current_logo)
            except Exception:
                logger.warning("Failed to delete company logo from S3. company_id=%s", profile.company_id)
        profile.logo_url = None
        profile.logo_path = None
        profile.updated_at = utc_now_naive()
        profile.updated_by = _audit_user(payload)
        await CompanyProfileRepository.save(session, profile)
        await session.commit()
        await ActivityLogService.create_log(
            session=session,
            actor={**payload, "role_code": "ROLE_EMPLOYER"},
            action="COMPANY_UPDATED",
            entity_type="Company",
            entity_id=profile.company_id,
            target_entity_name=getattr(profile, "company_name", None),
            description=f"Deleted company logo for {profile.company_name}",
        )
        return _serialize_company(profile)

    @staticmethod
    async def public_get(
        session: AsyncSession,
        company_id: str,
    ) -> CompanyProfileResponse:
        profile = await CompanyProfileRepository.get_public_by_id(session, company_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Company profile not found")
        return _serialize_company(profile)

    @staticmethod
    async def search(
        session: AsyncSession,
        name: Optional[str],
        industry: Optional[str],
        company_size: Optional[str],
        location: Optional[str],
        verification_status: Optional[str],
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
    ) -> CompanySearchResponse:
        if page < 1:
            raise HTTPException(status_code=400, detail="page must be greater than or equal to 1")
        if page_size < 1 or page_size > 100:
            raise HTTPException(status_code=400, detail="page_size must be between 1 and 100")
        rows, total = await CompanyProfileRepository.search(
            session=session,
            name=name,
            industry=industry,
            company_size=company_size,
            location=location,
            verification_status=verification_status,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return CompanySearchResponse(
            items=[_serialize_company(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
