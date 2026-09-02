import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from docx import Document
from fastapi import HTTPException
from reportlab.pdfgen import canvas

from app.service.candidate_service import CandidateProfileService
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.candidate_schema import CandidatePersonalInfoUpdateSchema, CandidateVisibilityUpdateSchema


def _make_pdf_bytes(text: str | None = "Jane Doe - Software Engineer") -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    if text:
        pdf.drawString(72, 800, text)
    pdf.save()
    return buffer.getvalue()


def _make_docx_bytes(text: str | None = "Jane Doe - Software Engineer") -> bytes:
    buffer = BytesIO()
    document = Document()
    if text:
        document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


class CapturingSession:
    def __init__(self):
        self.executed = []
        self.committed = False

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))

    async def commit(self):
        self.committed = True


def test_candidate_profile_defaults_search_engine_indexing_false():
    profile = CandidateProfile(user_id=uuid4())

    assert profile.search_engine_indexing is False


def test_visibility_schema_preserves_search_engine_indexing():
    payload = CandidateVisibilityUpdateSchema(search_engine_indexing=True)

    assert payload.model_dump()["search_engine_indexing"] is True


@pytest.mark.asyncio
async def test_get_full_profile_returns_backend_profile_and_cover_urls():
    user_id = uuid4()
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Sai",
        middle_name=None,
        last_name="Kiran",
        email="sai@example.com",
        mobile_number="9999999999",
        country_code="+91",
        profile_image_url=f"profile-images/{user_id}/profile.jpg",
        cover_image_url=f"profile-images/{user_id}/cover.jpg",
    )
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline="Backend Engineer",
        summary=None,
        country_id=None,
        primary_location_id=None,
        current_location=None,
        preferred_location_id=None,
        preferred_location=None,
        website_url=None,
        portfolio_url=None,
        experience_level=None,
        current_company=None,
        notice_period_id=None,
        notice_period=None,
        desired_employment=None,
        salary_expectation_id=None,
        salary_expectation=None,
        current_ctc=None,
        expected_ctc=None,
        work_preference=None,
        linkedin_url=None,
        dribbble_url=None,
        github_url=None,
        twitter_url=None,
        profile_visibility="PRIVATE",
        searchable_flag=True,
        open_to_work=True,
        search_engine_indexing=True,
        profile_completion_pct=20,
        active_resume_id=None,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.MasterDataRepo.get_candidate_target_roles",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await CandidateProfileService.get_full_profile(object(), user_id)

    assert result.profile_image_url == f"/profile-images/{user_id}/profile.jpg"
    assert result.cover_image_url == f"/profile-images/{user_id}/cover.jpg"
    assert result.open_to_work is True
    assert result.search_engine_indexing is True


@pytest.mark.asyncio
async def test_get_full_profile_handles_legacy_resume_json_and_nullable_profile_defaults():
    user_id = uuid4()
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Job",
        middle_name=None,
        last_name="Seeker",
        email="jobseeker@example.com",
        mobile_number=None,
        country_code=None,
        profile_image_url=None,
        cover_image_url=None,
    )
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline=None,
        summary=None,
        country_id=None,
        primary_location_id=None,
        current_location=None,
        preferred_location_id=None,
        preferred_location=None,
        website_url=None,
        portfolio_url=None,
        experience_level=None,
        current_company=None,
        notice_period_id=None,
        notice_period=None,
        desired_employment=None,
        salary_expectation_id=None,
        salary_expectation=None,
        current_ctc=None,
        expected_ctc=None,
        work_preference=None,
        linkedin_url=None,
        dribbble_url=None,
        github_url=None,
        twitter_url=None,
        profile_visibility=None,
        searchable_flag=None,
        open_to_work=None,
        profile_completion_pct=None,
        active_resume_id=None,
    )
    resume_detail = SimpleNamespace(
        education_json=[{"institution": "Osmania University"}],
        experience_json=[{"company": "NMK", "role": "Developer"}],
        skills_json=["Python", {"name": "FastAPI"}],
        certifications_json=["ignored-but-not-fatal"],
        projects_json=[{"title": "Job Portal"}],
        languages_json=["English"],
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
            new_callable=AsyncMock,
            return_value=resume_detail,
        ),
        patch(
            "app.service.candidate_service.MasterDataRepo.get_candidate_target_roles",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await CandidateProfileService.get_full_profile(object(), user_id)

    assert result.profile_visibility == "PRIVATE"
    assert result.searchable_flag is True
    assert result.open_to_work is False
    assert result.search_engine_indexing is False
    assert result.profile_completion_pct == 0
    assert result.skills[0].name == "Python"
    assert result.skills[0].skill_id.startswith("legacy-skill-")
    assert result.education[0].education_id.startswith("legacy-education-")
    assert result.experience[0].experience_id.startswith("legacy-experience-")
    assert result.projects[0].project_id.startswith("legacy-project-")
    assert result.languages[0].language_id.startswith("legacy-language-")


@pytest.mark.asyncio
async def test_update_visibility_persists_open_to_work_false():
    user_id = uuid4()
    session = object()
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        profile_visibility="PUBLIC",
        searchable_flag=True,
        open_to_work=True,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
    ):
        result = await CandidateProfileService.update_visibility(
            session,
            user_id,
            CandidateVisibilityUpdateSchema(open_to_work=False),
        )

    update_profile.assert_awaited_once_with(
        session=session,
        candidate_id="candidate-1",
        updated_by=str(user_id),
        open_to_work=False,
    )
    require_feature.assert_not_awaited()
    assert result["open_to_work"] is False


@pytest.mark.asyncio
async def test_update_visibility_persists_search_engine_indexing_true_with_other_fields():
    user_id = uuid4()
    session = object()
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        profile_visibility="PRIVATE",
        searchable_flag=False,
        open_to_work=False,
        search_engine_indexing=False,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
    ):
        result = await CandidateProfileService.update_visibility(
            session,
            user_id,
            CandidateVisibilityUpdateSchema(
                profile_visibility="PUBLIC",
                searchable_flag=True,
                open_to_work=True,
                search_engine_indexing=True,
            ),
        )

    update_profile.assert_awaited_once_with(
        session=session,
        candidate_id="candidate-1",
        updated_by=str(user_id),
        profile_visibility="PUBLIC",
        searchable_flag=True,
        open_to_work=True,
        search_engine_indexing=True,
    )
    require_feature.assert_awaited_once_with("resume_visibility")
    assert result["search_engine_indexing"] is True


@pytest.mark.asyncio
async def test_update_visibility_persists_search_engine_indexing_false():
    user_id = uuid4()
    session = object()
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        profile_visibility="PUBLIC",
        searchable_flag=True,
        open_to_work=True,
        search_engine_indexing=True,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ) as update_profile,
    ):
        result = await CandidateProfileService.update_visibility(
            session,
            user_id,
            CandidateVisibilityUpdateSchema(search_engine_indexing=False),
        )

    update_profile.assert_awaited_once_with(
        session=session,
        candidate_id="candidate-1",
        updated_by=str(user_id),
        search_engine_indexing=False,
    )
    require_feature.assert_not_awaited()
    assert result["search_engine_indexing"] is False


@pytest.mark.asyncio
async def test_update_personal_info_persists_phone_country_iso_for_shared_calling_code():
    user_id = uuid4()
    session = object()
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Jordan",
        middle_name=None,
        last_name="Blake",
        mobile_number="4155552671",
        country_code="+1",
        phone_country_iso2="US",
    )
    profile = SimpleNamespace(candidate_id="candidate-1", country_id=None)
    payload = CandidatePersonalInfoUpdateSchema(
        phone_number="4165552671",
        phone_country_code="+1",
        phone_country_iso2="CA",
    )

    with (
        patch(
            "app.service.candidate_service._get_user_or_404",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.service.candidate_service._get_profile_or_404",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_user",
            new_callable=AsyncMock,
        ) as update_user,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service._calc_completion",
            return_value=42,
        ),
    ):
        result = await CandidateProfileService.update_personal_info(session, user_id, payload)

    update_user.assert_awaited_once_with(
        session=session,
        user_id=user_id,
        updated_by=str(user_id),
        mobile_number="4165552671",
        country_code="+1",
        phone_country_iso2="CA",
    )
    assert result == {"message": "Personal info updated successfully", "profile_completion_pct": 42}


@pytest.mark.asyncio
async def test_update_visibility_requires_subscription_when_enabling_open_to_work():
    user_id = uuid4()
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        profile_visibility="PRIVATE",
        searchable_flag=False,
        open_to_work=False,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ),
    ):
        await CandidateProfileService.update_visibility(
            object(),
            user_id,
            CandidateVisibilityUpdateSchema(open_to_work=True),
        )

    require_feature.assert_awaited_once_with("resume_visibility")


@pytest.mark.asyncio
async def test_upload_profile_picture_persists_s3_key_on_user_record():
    user_id = uuid4()
    session = CapturingSession()
    s3_key = f"profile-images/{user_id}/profile.jpg"

    with (
        patch(
            "app.service.candidate_service.s3_service.upload_profile_picture",
            return_value=s3_key,
        ),
        patch(
            "app.service.candidate_service.s3_service.generate_presigned_url",
            return_value="https://signed.example/profile.jpg",
        ),
    ):
        result = await CandidateProfileService.upload_profile_picture(
            session=session,
            user_id=user_id,
            filename="profile.jpg",
            content_type="image/jpeg",
            contents=b"image-bytes",
        )

    assert session.committed is True
    assert session.executed[0][1] == {"url": s3_key, "uid": user_id}
    assert "UPDATE users SET profile_image_url = :url WHERE user_id = :uid" in session.executed[0][0]
    assert result == {
        "message": "Profile picture uploaded successfully",
        "url": "https://signed.example/profile.jpg",
    }


@pytest.mark.asyncio
async def test_upload_cover_picture_persists_s3_key_on_user_record():
    user_id = uuid4()
    session = CapturingSession()
    s3_key = f"profile-images/{user_id}/cover.jpg"

    with (
        patch(
            "app.service.candidate_service.s3_service.upload_cover_picture",
            return_value=s3_key,
        ),
        patch(
            "app.service.candidate_service.s3_service.generate_presigned_url",
            return_value="https://signed.example/cover.jpg",
        ),
    ):
        result = await CandidateProfileService.upload_cover_picture(
            session=session,
            user_id=user_id,
            filename="cover.jpg",
            content_type="image/jpeg",
            contents=b"image-bytes",
        )

    assert session.committed is True
    assert session.executed[0][1] == {"url": s3_key, "uid": user_id}
    assert "UPDATE users SET cover_image_url = :url WHERE user_id = :uid" in session.executed[0][0]
    assert result == {
        "message": "Cover picture uploaded successfully",
        "url": "https://signed.example/cover.jpg",
    }


class ResumeUploadSession(CapturingSession):
    """CapturingSession plus the add/flush/refresh hooks the ORM path needs."""

    def __init__(self):
        super().__init__()
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


@pytest.mark.asyncio
async def test_upload_resume_file_rejects_docx_with_no_content():
    """QA bug: an "empty" Word document (no text/tables/images) is still a
    non-trivial number of bytes as a zip container, so it must be rejected
    based on its actual content, not just its size."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    with pytest.raises(HTTPException) as exc_info:
        await CandidateProfileService.upload_resume_file(
            session=SimpleNamespace(),
            user_id=uuid4(),
            filename="Empty file.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            contents=_make_docx_bytes(text=None),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "The selected file is empty. Please upload a resume with content."


@pytest.mark.asyncio
async def test_upload_resume_file_rejects_pdf_with_no_content():
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    with pytest.raises(HTTPException) as exc_info:
        await CandidateProfileService.upload_resume_file(
            session=SimpleNamespace(),
            user_id=uuid4(),
            filename="resume.pdf",
            content_type="application/pdf",
            contents=_make_pdf_bytes(text=None),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "The selected file is empty. Please upload a resume with content."


@pytest.mark.asyncio
async def test_upload_resume_file_accepts_docx_with_content():
    """A .docx with real text should pass the content check and continue on
    to the rest of the upload flow (profile lookup, in this case)."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    with patch(
        "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_user_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await CandidateProfileService.upload_resume_file(
                session=SimpleNamespace(),
                user_id=uuid4(),
                filename="resume.docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                contents=_make_docx_bytes(),
            )

    # Content check passed; the flow reached the (mocked) profile lookup and
    # failed there instead, proving it wasn't rejected as empty.
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_resume_file_rejects_duplicate_upload():
    """QA bug: "Build Resume: User should not be able to upload the same
    file twice." Re-uploading a file whose content matches an existing,
    non-deleted resume must be rejected rather than silently creating a
    second copy."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    contents = _make_docx_bytes(text="Jane Doe - Software Engineer")
    file_hash = hashlib.sha256(contents).hexdigest()
    profile = SimpleNamespace(candidate_id="candidate-1")
    existing = SimpleNamespace(file_hash=file_hash)

    with patch(
        "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_resumes",
        new_callable=AsyncMock,
        return_value=[existing],
    ):
        with pytest.raises(HTTPException) as exc_info:
            await CandidateProfileService.upload_resume_file(
                session=SimpleNamespace(),
                user_id=uuid4(),
                filename="test124.docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                contents=contents,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "You've already uploaded this file. Please choose a different file."


@pytest.mark.asyncio
async def test_upload_resume_file_allows_different_content_with_same_name():
    """Re-uploading a *different* file that happens to share a name with an
    existing resume must NOT be treated as a duplicate -- only matching
    content should be rejected."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    profile = SimpleNamespace(candidate_id="candidate-1")
    existing = SimpleNamespace(file_hash=hashlib.sha256(b"a totally different file").hexdigest())

    with patch(
        "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_resumes",
        new_callable=AsyncMock,
        return_value=[existing],
    ):
        with pytest.raises(AttributeError):
            await CandidateProfileService.upload_resume_file(
                session=SimpleNamespace(),
                user_id=uuid4(),
                filename="test124.docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                contents=_make_docx_bytes(text="Jane Doe - Software Engineer"),
            )

    # Content didn't match the existing hash, so it wasn't rejected as a
    # duplicate -- it proceeded past that check and failed further down at
    # the (unmocked) session.execute DB update instead.


@pytest.mark.asyncio
async def test_upload_resume_file_subscription_limit_cannot_drop_below_five():
    """QA bug: candidates should always be able to upload up to
    MAX_RESUME_COUNT (5) resumes. A subscription plan's configured
    max_resume_uploads may raise that ceiling, but a lower/misconfigured
    plan value (e.g. 1) must never cap a candidate below the platform
    floor of 5."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    profile = SimpleNamespace(candidate_id="candidate-1")
    five_resumes = [SimpleNamespace(file_hash=f"hash-{i}", file_name=f"resume-{i}.pdf") for i in range(5)]

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resumes",
            new_callable=AsyncMock,
            return_value=five_resumes,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await CandidateProfileService.upload_resume_file(
                session=SimpleNamespace(),
                user_id=uuid4(),
                filename="test125.pdf",
                content_type="application/pdf",
                contents=_make_pdf_bytes(),
            )

    assert exc_info.value.status_code == 403
    assert "up to 5 resumes" in exc_info.value.detail



    """The job-application flow re-uses upload_resume_file with
    check_duplicate=False, since applying to multiple jobs with the same
    resume file is expected behaviour, not a mistaken duplicate upload."""
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    contents = _make_pdf_bytes()
    file_hash = hashlib.sha256(contents).hexdigest()
    profile = SimpleNamespace(candidate_id="candidate-1")
    existing = SimpleNamespace(file_hash=file_hash)
    session = ResumeUploadSession()

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resumes",
            new_callable=AsyncMock,
            return_value=[existing],
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.s3_service.upload_resume",
            return_value="resumes/candidate-1/resume.pdf",
        ),
    ):
        result = await CandidateProfileService.upload_resume_file(
            session=session,
            user_id=uuid4(),
            filename="resume.pdf",
            content_type="application/pdf",
            contents=contents,
            check_duplicate=False,
        )

    assert result.file_name == "resume.pdf"
    assert sum(isinstance(item, CandidateResume) for item in session.added) == 1


@pytest.mark.asyncio
async def test_upload_resume_file_captures_file_size_in_bytes():
    """QA bug: Download CV page should show file size before download.

    The size shown on that page comes from CandidateResume.file_size, which
    must be captured at upload time from the actual bytes received.
    """
    from app.model.authentication.mapper_bootstrap import bootstrap_mappers

    bootstrap_mappers()

    user_id = uuid4()
    session = ResumeUploadSession()
    profile = SimpleNamespace(candidate_id="candidate-1")
    contents = _make_pdf_bytes()

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resumes",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.s3_service.upload_resume",
            return_value="resumes/candidate-1/resume.pdf",
        ),
    ):
        result = await CandidateProfileService.upload_resume_file(
            session=session,
            user_id=user_id,
            filename="resume.pdf",
            content_type="application/pdf",
            contents=contents,
        )

    assert result.file_size == len(contents)
    resume_rows = [item for item in session.added if isinstance(item, CandidateResume)]
    assert len(resume_rows) == 1
    assert resume_rows[0].file_size == len(contents)


@pytest.mark.asyncio
async def test_get_resume_download_requests_attachment_presigned_url():
    """QA bug: clicking PDF/DOCX on the Download CV page opened a new tab
    that stole focus, so the "downloaded successfully" toast on the
    original tab went unseen. Forcing Content-Disposition: attachment on
    the presigned URL makes the browser save the file instead of opening
    a tab to render it, so focus (and the toast) stays on the original page.
    """
    user_id = uuid4()
    profile = SimpleNamespace(candidate_id="candidate-1")
    resume = SimpleNamespace(
        resume_id="resume-1",
        file_name="my-resume.pdf",
        file_path=None,
        blob_ref="resumes/candidate-1/resume-1.pdf",
        file_size=1234,
        is_active=True,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resume",
            new_callable=AsyncMock,
            return_value=resume,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.increment_resume_download_count",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.s3_service.generate_presigned_url",
            return_value="https://signed.example/resume-1.pdf",
        ) as presign,
    ):
        result = await CandidateProfileService.get_resume_download(
            session=object(), user_id=user_id, resume_id="resume-1"
        )

    presign.assert_called_once_with(
        "resumes/candidate-1/resume-1.pdf",
        expiry_seconds=3600,
        attachment_filename="my-resume.pdf",
    )
    assert result.file_path == "https://signed.example/resume-1.pdf"


@pytest.mark.asyncio
async def test_get_resume_preview_requests_inline_presigned_url():
    """The preview iframe must keep rendering the file inline, not force a
    download -- only the explicit "download" action should be an
    attachment."""
    user_id = uuid4()
    profile = SimpleNamespace(candidate_id="candidate-1")
    resume = SimpleNamespace(
        resume_id="resume-1",
        file_name="my-resume.pdf",
        file_path=None,
        blob_ref="resumes/candidate-1/resume-1.pdf",
        file_size=1234,
        is_active=True,
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resume",
            new_callable=AsyncMock,
            return_value=resume,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.increment_resume_download_count",
            new_callable=AsyncMock,
        ) as increment_count,
        patch(
            "app.service.candidate_service.s3_service.generate_presigned_url",
            return_value="https://signed.example/resume-1.pdf",
        ) as presign,
    ):
        await CandidateProfileService.get_resume_preview(
            session=object(), user_id=user_id, resume_id="resume-1"
        )

    presign.assert_called_once_with(
        "resumes/candidate-1/resume-1.pdf",
        expiry_seconds=3600,
        attachment_filename=None,
    )
    # Previews must never count towards the version's download_count.
    increment_count.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_personal_info_persists_phone_number():
    """Regression test: updating the Phone field on Edit Profile must persist
    the new number to Users.mobile_number, not silently drop it while still
    reporting success (see QA bug: 'Profile changes saved' toast but the old
    phone number reappears)."""
    from app.candidate_schema import CandidatePersonalInfoUpdateSchema

    user_id = uuid4()
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Sai",
        middle_name=None,
        last_name="Kiran",
        mobile_number="9999999999",
        country_code="+91",
    )
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        country_id=None,
        headline=None,
        summary=None,
        current_location=None,
        preferred_location=None,
        website_url=None,
        portfolio_url=None,
        linkedin_url=None,
        github_url=None,
        dribbble_url=None,
        twitter_url=None,
    )

    captured_user_update_kwargs = {}

    async def fake_update_user(session, user_id, updated_by, **kwargs):
        captured_user_update_kwargs.update(kwargs)

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_user",
            new=AsyncMock(side_effect=fake_update_user),
        ) as update_user_mock,
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        payload = CandidatePersonalInfoUpdateSchema(phone_number="8888877777")
        result = await CandidateProfileService.update_personal_info(
            session=None, user_id=user_id, data=payload
        )

    update_user_mock.assert_awaited_once()
    assert captured_user_update_kwargs.get("mobile_number") == "8888877777"
    # The in-memory `user` object must reflect the new number immediately so
    # a same-request re-read (or the completion-score calc below) sees it.
    assert user.mobile_number == "8888877777"
    assert result["message"] == "Personal info updated successfully"
