import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID
from app.utils.utc import utc_now_naive

from fastapi import HTTPException
from sqlalchemy.future import select
from sqlalchemy import func, or_, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
from app.model.candidate_model.candidate_saved_search import CandidateSavedSearch
from app.model.candidate_model.application_note import ApplicationNote
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.job_alert import JobAlert
from app.model.candidate_model.job_alert_notification_delivery import JobAlertNotificationDelivery
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.interview import Interview
from app.model.employer_model.job import Job
from app.model.employer_model.job_skill import JobSkill
from app.model.employer_model.shortlisted_candidate import ShortlistedCandidate
from app.utils.date_range import normalize_datetime_for_db


logger = logging.getLogger(__name__)


def _json_safe(value):
    """Recursively coerce values that pydantic's model_dump() can leave as
    non-JSON-native types (Decimal, date, datetime, UUID) into something the
    JSONB column's json.dumps() can actually serialize. Without this, any
    entry schema with a Decimal field (skills.years) or a date field
    (experience.start_date/end_date) raises 'Object of type X is not JSON
    serializable' the moment it's saved into one of these JSON list columns.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class CandidateProfileRepo:

    @classmethod
    async def get_profile_by_user_id(cls, session: AsyncSession, user_id: UUID) -> Optional[CandidateProfile]:
        query = (
            select(CandidateProfile)
            .where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted == False,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def get_latest_resume_detail(cls, session: AsyncSession, candidate_id: str) -> Optional[CandidateResumeDetail]:
        query = (
            select(CandidateResumeDetail)
            .where(
                CandidateResumeDetail.candidate_id == candidate_id,
                CandidateResumeDetail.is_deleted == False,
            )
            .order_by(CandidateResumeDetail.generated_at.desc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def get_user_by_id(cls, session: AsyncSession, user_id: UUID) -> Optional[Users]:
        query = (
            select(Users)
            .options(selectinload(Users.roles))
            .where(Users.user_id == user_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @classmethod
    async def create_profile_for_user(cls, session: AsyncSession, user_id: UUID) -> CandidateProfile:
        existing = await cls.get_profile_by_user_id(session, user_id)
        if existing:
            return existing

        profile = CandidateProfile(
            user_id=user_id,
            created_by=str(user_id),
            updated_by=str(user_id),
        )
        session.add(profile)
        await session.commit()
        return profile

    @classmethod
    async def list_public_candidates(
        cls,
        session: AsyncSession,
        search: Optional[str] = None,
        location: Optional[str] = None,
        skill: Optional[str] = None,
        experience_level: Optional[str] = None,
        work_preference: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        # This is the anonymous, no-login candidate directory, so it is
        # gated purely by the "Public link" (profile_visibility) toggle.
        # It intentionally does NOT depend on searchable_flag — that flag
        # controls recruiter search visibility, which is a separate,
        # independent setting (see EmployerCandidateSearchRepository).
        base = (
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                CandidateProfile.profile_visibility == "PUBLIC",
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )

        if search:
            term = f"%{search}%"
            base = base.where(
                or_(
                    Users.first_name.ilike(term),
                    Users.last_name.ilike(term),
                    CandidateProfile.headline.ilike(term),
                    CandidateProfile.current_company.ilike(term),
                    CandidateProfile.target_roles.ilike(term),
                )
            )
        if location:
            term = f"%{location}%"
            base = base.where(
                or_(
                    CandidateProfile.current_location.ilike(term),
                    CandidateProfile.preferred_location.ilike(term),
                )
            )
        if skill:
            base = base.where(CandidateProfile.skills_summary.ilike(f"%{skill}%"))
        if experience_level:
            base = base.where(CandidateProfile.experience_level == experience_level)
        if work_preference:
            base = base.where(CandidateProfile.work_preference == work_preference)

        total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        rows = await session.execute(
            base.order_by(CandidateProfile.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, rows.all()

    @classmethod
    async def get_public_candidate_detail(cls, session: AsyncSession, candidate_id: str):
        # Anonymous, no-login access (public share link). Gated only by the
        # "Public link" toggle (profile_visibility), independent of the
        # "Recruiter search" toggle (searchable_flag).
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                CandidateProfile.profile_visibility == "PUBLIC",
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )
        return result.one_or_none()

    @classmethod
    async def get_candidate_detail_for_employer(cls, session: AsyncSession, candidate_id: str):
        # Authenticated recruiter/employer access. Gated only by the
        # "Recruiter search" toggle (searchable_flag), independent of the
        # "Public link" toggle (profile_visibility). A candidate who has
        # recruiter search on but the public link off should still be
        # visible here.
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                CandidateProfile.searchable_flag.is_(True),
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )
        return result.one_or_none()

    @classmethod
    async def get_default_resume_for_employer_profile(
        cls,
        session: AsyncSession,
        candidate_id: str,
        active_resume_id: Optional[str],
    ) -> Optional[CandidateResume]:
        base = select(CandidateResume).where(
            CandidateResume.candidate_id == candidate_id,
            CandidateResume.is_deleted.is_(False),
        )
        if active_resume_id:
            result = await session.execute(
                base.where(CandidateResume.resume_id == active_resume_id)
            )
            resume = result.scalar_one_or_none()
            if resume:
                return resume

        result = await session.execute(
            base.where(CandidateResume.is_archived.is_(False))
            .order_by(CandidateResume.uploaded_at.desc())
            .limit(1)
        )
        resume = result.scalar_one_or_none()
        if resume:
            return resume

        result = await session.execute(
            base.order_by(CandidateResume.uploaded_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_employer_candidate_context(
        cls,
        session: AsyncSession,
        candidate_id: str,
        employer_user_id: UUID,
    ) -> dict:
        employer_id = await session.scalar(
            select(EmployerProfile.id).where(
                EmployerProfile.user_id == employer_user_id,
                EmployerProfile.is_deleted == 0,
            )
        )
        if not employer_id:
            return {
                "saved_candidate": False,
                "application": None,
                "interview": None,
                "notes_count": 0,
            }

        saved_candidate = await session.scalar(
            select(ShortlistedCandidate.shortlist_id)
            .where(
                ShortlistedCandidate.employer_id == employer_id,
                ShortlistedCandidate.candidate_id == candidate_id,
                ShortlistedCandidate.status == "ACTIVE",
            )
            .limit(1)
        )

        applications_result = await session.execute(
            select(JobApplication)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .order_by(JobApplication.updated_at.desc(), JobApplication.applied_at.desc())
        )
        applications = list(applications_result.scalars().all())
        application = applications[0] if applications else None
        application_ids = [item.application_id for item in applications]

        interview = None
        notes_count = 0
        if application_ids:
            interview_result = await session.execute(
                select(Interview)
                .where(Interview.application_id.in_(application_ids))
                .order_by(Interview.interview_date.desc(), Interview.interview_time.desc())
                .limit(1)
            )
            interview = interview_result.scalar_one_or_none()
            notes_count = int(
                await session.scalar(
                    select(func.count(ApplicationNote.note_id)).where(
                        ApplicationNote.application_id.in_(application_ids),
                        ApplicationNote.is_deleted.is_(False),
                    )
                )
                or 0
            )

        return {
            "saved_candidate": bool(saved_candidate),
            "application": application,
            "interview": interview,
            "notes_count": notes_count,
        }

    @classmethod
    async def get_candidate_profile_by_id(
        cls,
        session: AsyncSession,
        candidate_id: str,
    ) -> Optional[CandidateProfile]:
        result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def update_profile(cls, session: AsyncSession, candidate_id: str, updated_by: str, **kwargs):
        from datetime import datetime
        kwargs["updated_at"] = utc_now_naive()
        kwargs["updated_by"] = updated_by
        valid_columns = set(CandidateProfile.__table__.columns.keys())
        kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in valid_columns
        }

        query = (
            sql_update(CandidateProfile)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted == False,
            )
            .values(**kwargs)
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(query)
        await session.commit()

    @classmethod
    async def update_user(cls, session: AsyncSession, user_id: UUID, updated_by: str, **kwargs):
        from datetime import datetime
        kwargs["updated_by"] = UUID(updated_by) if updated_by else None
        kwargs["updated_at"] = utc_now_naive()

        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        query = (
            sql_update(Users)
            .where(Users.user_id == user_id)
            .values(**kwargs)
            .execution_options(synchronize_session="fetch")
        )
        try:
            await session.execute(query)
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            message = str(e).lower()
            if "uq_users_mobile" in message or "mobile_number" in message:
                raise HTTPException(status_code=400, detail="Mobile number already in use by another account!")
            raise

    @classmethod
    async def upsert_resume_detail(
        cls,
        session: AsyncSession,
        candidate_id: str,
        education_json: Optional[dict] = None,
        experience_json: Optional[dict] = None,
        skills_json: Optional[dict] = None,
        certifications_json: Optional[dict] = None,
        projects_json: Optional[dict] = None,
    ) -> CandidateResumeDetail:
        existing = await cls.get_latest_resume_detail(session, candidate_id)

        if existing:
            update_kwargs = {}
            if education_json is not None:
                update_kwargs["education_json"] = education_json
            if experience_json is not None:
                update_kwargs["experience_json"] = experience_json
            if skills_json is not None:
                update_kwargs["skills_json"] = skills_json
            if certifications_json is not None:
                update_kwargs["certifications_json"] = certifications_json
            if projects_json is not None:
                update_kwargs["projects_json"] = projects_json

            if update_kwargs:
                query = (
                    sql_update(CandidateResumeDetail)
                    .where(CandidateResumeDetail.resume_detail_id == existing.resume_detail_id)
                    .values(**update_kwargs)
                    .execution_options(synchronize_session="fetch")
                )
                await session.execute(query)
                await session.commit()

            return await cls.get_latest_resume_detail(session, candidate_id)

        else:
            new_detail = CandidateResumeDetail(
                candidate_id=candidate_id,
                education_json=education_json,
                experience_json=experience_json,
                skills_json=skills_json,
                certifications_json=certifications_json,
                projects_json=projects_json,
            )
            session.add(new_detail)
            await session.commit()
            return new_detail

    @classmethod
    async def get_or_create_resume_detail(cls, session: AsyncSession, candidate_id: str) -> CandidateResumeDetail:
        existing = await cls.get_latest_resume_detail(session, candidate_id)
        if existing:
            return existing
        new_detail = CandidateResumeDetail(candidate_id=candidate_id)
        session.add(new_detail)
        await session.commit()
        return new_detail

    @classmethod
    async def _set_json_list(cls, session: AsyncSession, candidate_id: str, json_column: str, list_key: str, items: list) -> None:
        detail = await cls.get_or_create_resume_detail(session, candidate_id)
        safe_items = _json_safe(items)
        query = (
            sql_update(CandidateResumeDetail)
            .where(CandidateResumeDetail.resume_detail_id == detail.resume_detail_id)
            .values(**{json_column: {list_key: safe_items}})
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(query)
        await session.commit()

    @classmethod
    async def add_json_list_item(
        cls,
        session: AsyncSession,
        candidate_id: str,
        json_column: str,
        list_key: str,
        item: dict,
    ) -> dict:
        """Append a single entry (with a generated id) to a JSON list column on CandidateResumeDetail."""
        detail = await cls.get_or_create_resume_detail(session, candidate_id)
        current = (getattr(detail, json_column) or {}).get(list_key, [])
        current = list(current)
        current.append(item)
        await cls._set_json_list(session, candidate_id, json_column, list_key, current)
        return item

    @classmethod
    async def update_json_list_item(
        cls,
        session: AsyncSession,
        candidate_id: str,
        json_column: str,
        list_key: str,
        item_id_field: str,
        item_id: str,
        updates: dict,
    ) -> Optional[dict]:
        """Patch a single entry (matched by its id field) within a JSON list column."""
        detail = await cls.get_latest_resume_detail(session, candidate_id)
        if not detail:
            return None
        current = list((getattr(detail, json_column) or {}).get(list_key, []))
        updated_item = None
        for idx, entry in enumerate(current):
            if entry.get(item_id_field) == item_id:
                # `updates` only contains keys the client explicitly sent (see
                # CandidateSkillUpdateSchema usage with exclude_unset=True), so a
                # key present here with value None means the user intentionally
                # cleared that field and it must overwrite the stored value.
                # Only keys the client never sent should be left untouched.
                merged = {**entry, **updates}
                current[idx] = merged
                updated_item = merged
                break
        if updated_item is None:
            return None
        await cls._set_json_list(session, candidate_id, json_column, list_key, current)
        return updated_item

    @classmethod
    async def delete_json_list_item(
        cls,
        session: AsyncSession,
        candidate_id: str,
        json_column: str,
        list_key: str,
        item_id_field: str,
        item_id: str,
    ) -> bool:
        """Remove a single entry (matched by its id field) from a JSON list column."""
        detail = await cls.get_latest_resume_detail(session, candidate_id)
        if not detail:
            return False
        current = list((getattr(detail, json_column) or {}).get(list_key, []))
        new_list = [entry for entry in current if entry.get(item_id_field) != item_id]
        if len(new_list) == len(current):
            return False
        await cls._set_json_list(session, candidate_id, json_column, list_key, new_list)
        return True

    @classmethod
    async def get_resumes(cls, session: AsyncSession, candidate_id: str) -> list[CandidateResume]:
        result = await session.execute(
            select(CandidateResume)
            .where(
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
            .order_by(CandidateResume.uploaded_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_most_recent_resume(
        cls, session: AsyncSession, candidate_id: str, exclude_resume_id: Optional[str] = None
    ) -> Optional[CandidateResume]:
        """Used as the fallback "default" resume when no resume has been
        explicitly marked active/default: the most recently uploaded,
        non-archived, non-deleted resume. Falls back further to the most
        recently uploaded resume regardless of archive state if every
        resume happens to be archived, so a candidate with resumes never
        ends up with no previewable/downloadable default."""
        base_query = select(CandidateResume).where(
            CandidateResume.candidate_id == candidate_id,
            CandidateResume.is_deleted.is_(False),
        )
        if exclude_resume_id:
            base_query = base_query.where(CandidateResume.resume_id != exclude_resume_id)

        active_query = base_query.where(CandidateResume.is_archived.is_(False)).order_by(
            CandidateResume.uploaded_at.desc()
        )
        result = await session.execute(active_query)
        resume = result.scalars().first()
        if resume:
            return resume

        fallback_query = base_query.order_by(CandidateResume.uploaded_at.desc())
        result = await session.execute(fallback_query)
        return result.scalars().first()

    @classmethod
    async def get_resume(cls, session: AsyncSession, candidate_id: str, resume_id: str) -> Optional[CandidateResume]:
        result = await session.execute(
            select(CandidateResume).where(
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.resume_id == resume_id,
                CandidateResume.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def set_active_resume(cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID) -> bool:
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return False
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.candidate_id == candidate_id)
            .values(is_active=False, updated_by=str(user_id))
        )
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(is_active=True, updated_by=str(user_id))
        )
        await session.execute(
            sql_update(CandidateProfile)
            .where(CandidateProfile.candidate_id == candidate_id)
            .values(active_resume_id=resume_id, updated_by=str(user_id))
        )
        await session.commit()
        return True

    @classmethod
    async def delete_resume(cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID) -> bool:
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return False
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(is_deleted=True, is_active=False, deleted_at=utc_now_naive(), updated_by=str(user_id))
        )
        if resume.is_active:
            await session.execute(
                sql_update(CandidateProfile)
                .where(CandidateProfile.candidate_id == candidate_id)
                .values(active_resume_id=None, updated_by=str(user_id))
            )
        await session.commit()
        return True

    @classmethod
    async def update_resume_meta(
        cls,
        session: AsyncSession,
        candidate_id: str,
        resume_id: str,
        user_id: UUID,
        values: dict,
    ) -> Optional[CandidateResume]:
        """Patch version_name / template / notes on a resume version."""
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        clean_values = {k: v for k, v in values.items() if v is not None}
        if not clean_values:
            return resume
        clean_values["updated_by"] = str(user_id)
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(**clean_values)
        )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def set_resume_archived(
        cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID, archived: bool
    ) -> Optional[CandidateResume]:
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(is_archived=archived, updated_by=str(user_id))
        )
        # A resume can't stay the active/default one while archived.
        if archived and resume.is_active:
            await session.execute(
                sql_update(CandidateResume)
                .where(CandidateResume.resume_id == resume_id)
                .values(is_active=False)
            )
            await session.execute(
                sql_update(CandidateProfile)
                .where(CandidateProfile.candidate_id == candidate_id)
                .values(active_resume_id=None, updated_by=str(user_id))
            )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def duplicate_resume(
        cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID
    ) -> Optional[CandidateResume]:
        source = await cls.get_resume(session, candidate_id, resume_id)
        if not source:
            return None
        highest = await session.execute(
            select(func.max(CandidateResume.version_no)).where(CandidateResume.candidate_id == candidate_id)
        )
        next_version_no = (highest.scalar() or source.version_no or 0) + 1
        copy = CandidateResume(
            candidate_id=candidate_id,
            version_no=next_version_no,
            file_name=source.file_name,
            file_path=source.file_path,
            blob_ref=source.blob_ref,
            file_size=source.file_size,
            file_hash=source.file_hash,
            is_active=False,
            version_name=f"{source.version_name or source.file_name or 'Resume'} (Copy)",
            template=source.template,
            notes=source.notes,
            usage_note=source.usage_note,
            created_by=str(user_id),
            updated_by=str(user_id),
        )
        session.add(copy)
        await session.commit()
        await session.refresh(copy)
        return copy

    @classmethod
    async def set_resume_share_link(
        cls,
        session: AsyncSession,
        candidate_id: str,
        resume_id: str,
        user_id: UUID,
        share_token: str,
        requires_email: bool,
        expires_at: Optional[datetime],
    ) -> Optional[CandidateResume]:
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(
                share_token=share_token,
                share_enabled=True,
                share_requires_email=requires_email,
                share_expires_at=expires_at,
                updated_by=str(user_id),
            )
        )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def disable_resume_share_link(
        cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID
    ) -> Optional[CandidateResume]:
        """Turn a share link off without discarding it -- the token, expiry,
        and email-gate setting are all preserved so `enable_resume_share_link`
        can turn the exact same URL back on later."""
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(share_enabled=False, updated_by=str(user_id))
        )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def enable_resume_share_link(
        cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID
    ) -> Optional[CandidateResume]:
        """Re-activate a previously disabled link, reusing the existing
        share_token so the same URL the candidate already shared works again."""
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(share_enabled=True, updated_by=str(user_id))
        )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def delete_resume_share_link(
        cls, session: AsyncSession, candidate_id: str, resume_id: str, user_id: UUID
    ) -> Optional[CandidateResume]:
        """Permanently remove the share link: clears the token/expiry/email-gate
        so the old URL can never be reactivated. A later 'Create link' click
        will mint a brand-new token."""
        resume = await cls.get_resume(session, candidate_id, resume_id)
        if not resume:
            return None
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(
                share_enabled=False,
                share_token=None,
                share_requires_email=False,
                share_expires_at=None,
                share_view_count=0,
                updated_by=str(user_id),
            )
        )
        await session.commit()
        return await cls.get_resume(session, candidate_id, resume_id)

    @classmethod
    async def increment_resume_download_count(cls, session: AsyncSession, resume_id: str) -> None:
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(download_count=CandidateResume.download_count + 1)
        )
        await session.commit()

    @classmethod
    async def get_resume_by_share_token(cls, session: AsyncSession, share_token: str) -> Optional[CandidateResume]:
        """Public lookup used by the /cv/{token} share page -- deliberately
        not scoped to a candidate_id since the whole point is that this is
        reachable by anyone holding the link."""
        result = await session.execute(
            select(CandidateResume).where(
                CandidateResume.share_token == share_token,
                CandidateResume.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def increment_resume_share_view_count(cls, session: AsyncSession, resume_id: str) -> None:
        await session.execute(
            sql_update(CandidateResume)
            .where(CandidateResume.resume_id == resume_id)
            .values(share_view_count=CandidateResume.share_view_count + 1)
        )
        await session.commit()

    @classmethod
    async def get_skills_for_jobs(cls, session: AsyncSession, job_ids: list[str]) -> dict[str, list[str]]:
        """job_id -> ordered list of skill strings (e.g. ["Java", "Spring Boot"]),
        used to group Saved/Favourite Jobs by role instead of a hardcoded list."""
        if not job_ids:
            return {}
        rows = await session.execute(
            select(JobSkill.job_id, JobSkill.skill).where(JobSkill.job_id.in_(job_ids))
        )
        skills_by_job: dict[str, list[str]] = {}
        for job_id, skill in rows.all():
            skills_by_job.setdefault(job_id, []).append(skill)
        return skills_by_job

    @classmethod
    async def get_saved_jobs(cls, session: AsyncSession, candidate_id: str, page: int, page_size: int):
        base = (
            select(CandidateSavedJob, Job)
            .join(Job, Job.job_id == CandidateSavedJob.job_id)
            .where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.saved_flag.is_(True),
                CandidateSavedJob.deleted_at.is_(None),
                Job.is_deleted.is_(False),
            )
        )
        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        rows = await session.execute(
            base.order_by(CandidateSavedJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = rows.all()
        skills_by_job = await cls.get_skills_for_jobs(session, [job.job_id for _, job in rows])
        return total, rows, skills_by_job

    @classmethod
    async def is_job_saved(cls, session: AsyncSession, candidate_id: str, job_id: str) -> bool:
        result = await session.execute(
            select(CandidateSavedJob.saved_job_id).where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.job_id == job_id,
                CandidateSavedJob.saved_flag.is_(True),
                CandidateSavedJob.deleted_at.is_(None),
                CandidateSavedJob.job_id.in_(
                    select(Job.job_id).where(Job.is_deleted.is_(False))
                ),
            )
        )
        return result.scalar_one_or_none() is not None

    @classmethod
    async def count_saved_jobs(cls, session: AsyncSession, candidate_id: str) -> int:
        result = await session.execute(
            select(func.count()).select_from(
                select(CandidateSavedJob.saved_job_id).where(
                    CandidateSavedJob.candidate_id == candidate_id,
                    CandidateSavedJob.saved_flag.is_(True),
                    CandidateSavedJob.deleted_at.is_(None),
                    CandidateSavedJob.job_id.in_(
                        select(Job.job_id).where(Job.is_deleted.is_(False))
                    ),
                ).subquery()
            )
        )
        return result.scalar_one()

    @classmethod
    async def save_job(cls, session: AsyncSession, candidate_id: str, job_id: str) -> CandidateSavedJob:
        job_result = await session.execute(
            select(Job.job_id).where(
                Job.job_id == job_id,
                Job.is_deleted.is_(False),
            )
        )
        if job_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Job is no longer available.")

        result = await session.execute(
            select(CandidateSavedJob).where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.job_id == job_id,
            )
        )
        saved = result.scalar_one_or_none()
        if saved:
            saved.saved_flag = True
            saved.deleted_at = None
        else:
            saved = CandidateSavedJob(candidate_id=candidate_id, job_id=job_id)
            session.add(saved)
        await session.commit()
        return saved

    @classmethod
    async def unsave_job(cls, session: AsyncSession, candidate_id: str, job_id: str) -> bool:
        result = await session.execute(
            sql_update(CandidateSavedJob)
            .where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.job_id == job_id,
                CandidateSavedJob.saved_flag.is_(True),
            )
            .values(saved_flag=False, deleted_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def get_job_alerts(cls, session: AsyncSession, candidate_id: str) -> list[JobAlert]:
        result = await session.execute(
            select(JobAlert)
            .where(JobAlert.candidate_id == candidate_id)
            .order_by(JobAlert.created_at.desc())
        )
        return list(result.scalars().all())

    
    @classmethod
    async def create_job_alert(
        cls,
        session: AsyncSession,
        candidate_id: str,
        **kwargs,
    ) -> JobAlert:

        alert = JobAlert(
            candidate_id=candidate_id,
            **kwargs,
        )

        session.add(alert)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(
                "Failed to create candidate job alert.",
                extra={"error_type": e.__class__.__name__},
            )
            raise

        await session.refresh(alert)

        return alert
    @classmethod
    async def find_duplicate_job_alert(
        cls,
        session: AsyncSession,
        candidate_id: str,
        title: str,
        job_category: str,
        job_title: Optional[str],
        preferred_location: Optional[str],
        experience_level: str,
        employment_type: str,
    ) -> Optional[JobAlert]:

        result = await session.execute(
            select(JobAlert).where(
                JobAlert.candidate_id == candidate_id,
                JobAlert.title == title,
                JobAlert.job_category == job_category,
                JobAlert.job_title == job_title,
                JobAlert.preferred_location == preferred_location,
                JobAlert.experience_level == experience_level,
                JobAlert.employment_type == employment_type,
                JobAlert.is_active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def find_job_alert_by_title(
        cls,
        session: AsyncSession,
        candidate_id: str,
        title: str,
        exclude_alert_id: Optional[str] = None,
    ) -> Optional[JobAlert]:
        normalized_title = (title or "").strip().lower()
        if not normalized_title:
            return None

        conditions = [
            JobAlert.candidate_id == candidate_id,
            func.lower(func.trim(JobAlert.title)) == normalized_title,
        ]
        if exclude_alert_id:
            conditions.append(JobAlert.alert_id != exclude_alert_id)

        result = await session.execute(
            select(JobAlert).where(*conditions).limit(1)
        )

        return result.scalars().first()
    
    @classmethod
    async def update_job_alert(
        cls,
        session: AsyncSession,
        candidate_id: str,
        alert_id: str,
        **kwargs,
    ) -> Optional[JobAlert]:

        # Remove None values so only supplied fields are updated
        kwargs = {
            key: value
            for key, value in kwargs.items()
            if value is not None or key in {"preferred_location", "job_category", "job_title"}
        }

        # Nothing to update
        if not kwargs:
            result = await session.execute(
                select(JobAlert).where(
                    JobAlert.candidate_id == candidate_id,
                    JobAlert.alert_id == alert_id,
                )
            )
            return result.scalar_one_or_none()

        # Update timestamp

        result = await session.execute(
            sql_update(JobAlert)
            .where(
                JobAlert.candidate_id == candidate_id,
                JobAlert.alert_id == alert_id,
            )
            .values(**kwargs)
            .execution_options(synchronize_session="fetch")
        )

        if result.rowcount == 0:
            await session.rollback()
            return None

        await session.commit()

        result = await session.execute(
            select(JobAlert).where(
                JobAlert.alert_id == alert_id
            )
        )

        return result.scalar_one_or_none()
    @classmethod
    async def get_job_alert(
        cls,
        session: AsyncSession,
        candidate_id: str,
        alert_id: str,
    ) -> Optional[JobAlert]:

        result = await session.execute(
            select(JobAlert).where(
                JobAlert.candidate_id == candidate_id,
                JobAlert.alert_id == alert_id,
            )
        )

        return result.scalar_one_or_none()
    
    @classmethod
    async def get_active_job_alert_candidates(
        cls,
        session: AsyncSession,
    ):
        """
        Returns all active job alerts (any notification_preference) with
        candidate name, email, and the recipient's user_id.

        Note: this used to filter on notification_preference == "EMAIL" and
        omit `frequency` / `user_id` from the SELECT, which silently broke
        the entire job-alert notification flow — see
        JobAlertNotificationService for how these columns are used.
        """

        result = await session.execute(
            select(
                JobAlert.alert_id,
                JobAlert.candidate_id,
                JobAlert.title,
                JobAlert.job_category,
                JobAlert.job_title,
                JobAlert.preferred_location,
                JobAlert.employment_type,
                JobAlert.experience_level,
                JobAlert.notification_preference,
                JobAlert.frequency,
                JobAlert.timezone,
                CandidateProfile.user_id,
                Users.first_name,
                Users.last_name,
                Users.email,
            )
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == JobAlert.candidate_id,
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id,
            )
            .where(
                JobAlert.is_active.is_(True),
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )

        return result.all()

    @classmethod
    async def get_active_job_alert_candidates_by_frequency(
        cls,
        session: AsyncSession,
        frequency: str,
    ):
        result = await session.execute(
            select(
                JobAlert.alert_id,
                JobAlert.candidate_id,
                JobAlert.title,
                JobAlert.job_category,
                JobAlert.job_title,
                JobAlert.preferred_location,
                JobAlert.employment_type,
                JobAlert.experience_level,
                JobAlert.notification_preference,
                JobAlert.frequency,
                JobAlert.timezone,
                CandidateProfile.user_id,
                Users.first_name,
                Users.last_name,
                Users.email,
            )
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == JobAlert.candidate_id,
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id,
            )
            .where(
                JobAlert.is_active.is_(True),
                JobAlert.frequency == frequency,
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )

        return result.all()

    @classmethod
    async def get_jobs_posted_between(
        cls,
        session: AsyncSession,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Job]:
        start_at = normalize_datetime_for_db(start_at)
        end_at = normalize_datetime_for_db(end_at)

        result = await session.execute(
            select(Job)
            .where(
                Job.created_at >= start_at,
                Job.created_at <= end_at,
                Job.status == "PUBLISHED",
                Job.is_deleted.is_(False),
            )
            .order_by(Job.created_at.asc())
        )

        return list(result.scalars().all())

    @classmethod
    async def delete_job_alert(
        cls,
        session: AsyncSession,
        candidate_id: str,
        alert_id: str,
    ) -> bool:

        result = await session.execute(
            select(JobAlert).where(
                JobAlert.candidate_id == candidate_id,
                JobAlert.alert_id == alert_id,
            )
        )

        alert = result.scalar_one_or_none()

        if not alert:
            return False

        try:
            await session.execute(
                sql_update(JobAlertNotificationDelivery)
                .where(JobAlertNotificationDelivery.alert_id == alert_id)
                .values(alert_id=None)
                .execution_options(synchronize_session=False)
            )
            await session.delete(alert)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return True

    @classmethod
    async def get_saved_searches(cls, session: AsyncSession, candidate_id: str) -> list[CandidateSavedSearch]:
        result = await session.execute(
            select(CandidateSavedSearch)
            .where(CandidateSavedSearch.candidate_id == candidate_id)
            .order_by(CandidateSavedSearch.updated_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create_saved_search(cls, session: AsyncSession, candidate_id: str, **kwargs) -> CandidateSavedSearch:
        saved_search = CandidateSavedSearch(candidate_id=candidate_id, **kwargs)
        session.add(saved_search)
        await session.commit()
        return saved_search
