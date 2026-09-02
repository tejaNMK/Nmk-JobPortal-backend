import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only
from app.main import init_app
from app.repository.candidate_repo import CandidateProfileRepo
from app.schema.job_applicants import ApplicantFilterParams
from app.service.candidate_service import CandidateProfileService
from app.service.employer_service.job_applicants_service import (
    JobApplicantsService,
)


class FakeSession:
    pass


@pytest.fixture()
def employer_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "hr@example.com",
        }

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    app.dependency_overrides[employer_user_only] = fake_payload
    return TestClient(app)


def test_employer_applicant_download_file_route_requires_owned_application(employer_client):
    with patch(
        "app.controller.employer_controller.job_applicants."
        "JobApplicantsService.get_resume_file",
        new_callable=AsyncMock,
        return_value=(b"%PDF-1.4", "alice-resume.pdf", "application/pdf"),
    ) as service:
        response = employer_client.get(
            "/employer/job-applicants/app-1/resume/download-file",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4"
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment" in response.headers["content-disposition"]
    service.assert_awaited_once()


def test_employer_can_update_applicant_status_from_applicants_route(employer_client):
    with patch(
        "app.controller.employer_controller.job_applicants."
        "JobApplicantsService.update_application_status",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            model_dump=lambda: {
                "application_id": "app-1",
                "application_status": "REJECTED",
                "updated_at": "2026-07-30T12:34:56Z",
            }
        ),
    ) as service:
        response = employer_client.patch(
            "/employer/job-applicants/app-1/status",
            json={"status": "REJECTED", "reason": "Role closed"},
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Application status updated successfully"
    assert body["data"] == {
        "application_id": "app-1",
        "application_status": "REJECTED",
        "updated_at": "2026-07-30T12:34:56Z",
    }
    service.assert_awaited_once()


def test_employer_applicant_status_route_validates_allowed_status(employer_client):
    response = employer_client.patch(
        "/employer/job-applicants/app-1/status",
        json={"status": "SHORTLISTED"},
        headers={"Authorization": "Bearer jwt-token"},
    )

    assert response.status_code == 422


def test_employer_applicant_list_includes_candidate_id():
    user_id = uuid4()
    candidate_user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    row = (
        SimpleNamespace(
            application_id="app-1",
            referral_contact=None,
            source=None,
            applied_at=datetime(2026, 8, 1, 10, 0, 0),
            application_status="APPLIED",
        ),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(
            first_name="Alice",
            middle_name=None,
            last_name="Example",
            email="alice@example.com",
            mobile_number="9999999999",
            profile_image_url=f"profile-images/{candidate_user_id}/profile.jpg",
        ),
        SimpleNamespace(file_name="alice-resume.pdf"),
        SimpleNamespace(job_id="job-1", title="Backend Engineer"),
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_job_applicants",
        new_callable=AsyncMock,
        return_value=(1, [row]),
    ):
        result = asyncio.run(
            JobApplicantsService.list_applicants(
                session=SimpleNamespace(),
                user_id=user_id,
                filters=ApplicantFilterParams(),
            )
        )

    assert result.items[0].application_id == "app-1"
    assert result.items[0].candidate_id == "candidate-1"
    assert (
        result.items[0].profile_image_url
        == f"/profile-images/{candidate_user_id}/profile.jpg"
    )
    assert result.items[0].view_profile_url == "/employer/job-applicants/app-1"
    assert result.items[0].download_resume_url == "/employer/job-applicants/app-1/resume/download-file"


def test_employer_applicant_list_best_match_ranks_items_and_adds_match_fields():
    user_id = uuid4()
    rows = [
        (
            SimpleNamespace(
                application_id="app-low",
                referral_contact=None,
                source=None,
                applied_at=datetime(2026, 8, 1, 10, 0, 0),
                application_status="APPLIED",
            ),
            SimpleNamespace(candidate_id="candidate-low"),
            SimpleNamespace(
                first_name="Low",
                middle_name=None,
                last_name="Match",
                email="low@example.com",
                mobile_number=None,
                profile_image_url=None,
            ),
            None,
            SimpleNamespace(job_id="job-1", title="Backend Engineer"),
            None,
        ),
        (
            SimpleNamespace(
                application_id="app-high",
                referral_contact=None,
                source=None,
                applied_at=datetime(2026, 8, 2, 10, 0, 0),
                application_status="APPLIED",
            ),
            SimpleNamespace(candidate_id="candidate-high"),
            SimpleNamespace(
                first_name="High",
                middle_name=None,
                last_name="Match",
                email="high@example.com",
                mobile_number=None,
                profile_image_url=None,
            ),
            None,
            SimpleNamespace(job_id="job-1", title="Backend Engineer"),
            None,
        ),
    ]

    async def fake_rank(**kwargs):
        score = 92 if kwargs["application"].application_id == "app-high" else 48
        return SimpleNamespace(
            match_score=score,
            match_label="Strong Match" if score == 92 else "Low Match",
            match_reasons=["Relevant backend experience"],
            missing_requirements=[],
        )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_job_applicants",
        new_callable=AsyncMock,
        return_value=(2, rows),
    ) as get_applicants, patch(
        "app.service.employer_service.job_applicants_service."
        "ApplicantRankingService.rank_applicant",
        new_callable=AsyncMock,
        side_effect=fake_rank,
    ):
        result = asyncio.run(
            JobApplicantsService.list_applicants(
                session=SimpleNamespace(),
                user_id=user_id,
                filters=ApplicantFilterParams(ai_rank=True),
            )
        )

    assert [item.application_id for item in result.items] == ["app-high", "app-low"]
    assert get_applicants.await_args.kwargs["ranking_limit"] == 20
    assert result.items[0].match_score == 92
    assert result.items[0].match_label == "Strong Match"
    assert result.items[0].match_reasons == ["Relevant backend experience"]


def test_employer_applicant_list_does_not_rank_without_ai_rank_button():
    user_id = uuid4()
    row = (
        SimpleNamespace(
            application_id="app-1",
            referral_contact=None,
            source=None,
            applied_at=datetime(2026, 8, 1, 10, 0, 0),
            application_status="APPLIED",
        ),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(
            first_name="Alice",
            middle_name=None,
            last_name="Example",
            email="alice@example.com",
            mobile_number=None,
            profile_image_url=None,
        ),
        None,
        SimpleNamespace(job_id="job-1", title="Backend Engineer"),
        None,
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_job_applicants",
        new_callable=AsyncMock,
        return_value=(1, [row]),
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ) as require_feature, patch(
        "app.service.employer_service.job_applicants_service."
        "ApplicantRankingService.rank_applicant",
        new_callable=AsyncMock,
    ) as rank:
        result = asyncio.run(
            JobApplicantsService.list_applicants(
                session=SimpleNamespace(),
                user_id=user_id,
                filters=ApplicantFilterParams(sort_by="best_match", ai_rank=False),
            )
        )

    require_feature.assert_not_awaited()
    rank.assert_not_awaited()
    assert result.items[0].match_score is None
    assert result.items[0].match_reasons == []


@pytest.mark.parametrize("status", ["REJECTED", "APPLIED"])
def test_employer_applicant_status_service_updates_application_directly(status):
    user_id = uuid4()
    updated_at = datetime(2026, 7, 30, 12, 34, 56)
    application = SimpleNamespace(
        application_id="app-1",
        application_status="APPLIED",
        updated_at=updated_at,
    )
    updated_application = SimpleNamespace(
        application_id="app-1",
        application_status=status,
        updated_at=updated_at,
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=application,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.update_application_status",
        new_callable=AsyncMock,
        return_value=updated_application,
    ) as update_status:
        result = asyncio.run(
            JobApplicantsService.update_application_status(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
                payload=SimpleNamespace(status=status, reason="Changed by recruiter"),
            )
        )

    assert result.application_id == "app-1"
    assert result.application_status == status
    assert result.updated_at == "2026-07-30T12:34:56Z"
    update_status.assert_awaited_once()
    assert update_status.await_args.kwargs["application"] is application
    assert update_status.await_args.kwargs["status"] == status
    assert update_status.await_args.kwargs["reason"] == "Changed by recruiter"


def test_employer_applicant_profile_does_not_expose_resume_storage_path():
    user_id = uuid4()
    row = (
        SimpleNamespace(
            application_id="app-1",
            referral_contact=None,
            source=None,
            applied_at=datetime(2026, 8, 1, 10, 0, 0),
            application_status="APPLIED",
        ),
        SimpleNamespace(
            candidate_id="candidate-1",
            headline="Senior Backend Engineer",
            summary="Builds APIs.",
            total_experience=8,
            current_location="Remote",
            preferred_location="Remote",
            skills_summary="Python, FastAPI",
        ),
        SimpleNamespace(
            first_name="Alice",
            middle_name=None,
            last_name="Example",
            email="alice@example.com",
            mobile_number="9999999999",
            profile_image_url=None,
        ),
        SimpleNamespace(
            resume_id="resume-1",
            file_name="alice-resume.pdf",
            file_path="/internal/private/alice-resume.pdf",
        ),
        SimpleNamespace(job_id="job-1", title="Backend Engineer"),
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_details",
        new_callable=AsyncMock,
        return_value=row,
    ):
        result = asyncio.run(
            JobApplicantsService.get_applicant_profile(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
            )
        )

    dumped = result.model_dump()
    assert "resume_path" not in dumped
    assert result.has_resume is True
    assert result.view_resume_url == "/employer/job-applicants/app-1/resume/preview-file"
    assert result.download_resume_url == "/employer/job-applicants/app-1/resume/download-file"


def test_employer_resume_metadata_returns_authorized_api_urls_not_storage_path():
    user_id = uuid4()
    row = (
        SimpleNamespace(application_id="app-1"),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(),
        SimpleNamespace(
            resume_id="resume-1",
            file_name="alice-resume.pdf",
            file_path="/internal/private/alice-resume.pdf",
            file_size=1024,
        ),
        SimpleNamespace(),
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_details",
        new_callable=AsyncMock,
        return_value=row,
    ):
        result = asyncio.run(
            JobApplicantsService.get_resume(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
            )
        )

    assert result.file_path is None
    assert result.file_size == 1024
    assert result.is_previewable is True
    assert result.download_url == "/employer/job-applicants/app-1/resume/download-file"


def test_employer_resume_file_fetches_application_resume_blob():
    user_id = uuid4()
    row = (
        SimpleNamespace(application_id="app-1"),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(),
        SimpleNamespace(
            resume_id="resume-1",
            file_name="alice-resume.pdf",
            blob_ref="resumes/candidate-1/resume-1.pdf",
        ),
        SimpleNamespace(),
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_details",
        new_callable=AsyncMock,
        return_value=row,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "s3_service.fetch_object_bytes",
        return_value=(b"%PDF-1.4", "application/pdf"),
    ) as fetch:
        content, filename, content_type = asyncio.run(
            JobApplicantsService.get_resume_file(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
            )
        )

    assert content == b"%PDF-1.4"
    assert filename == "alice-resume.pdf"
    assert content_type == "application/pdf"
    fetch.assert_called_once_with("resumes/candidate-1/resume-1.pdf")


def test_employer_resume_file_uses_application_resume_snapshot_when_resume_missing():
    user_id = uuid4()
    row = (
        SimpleNamespace(
            application_id="app-1",
            resume_id="resume-1",
            resume_file_name_snapshot="alice-resume.pdf",
            resume_file_path_snapshot=None,
            resume_blob_ref_snapshot="resumes/candidate-1/snapshot.pdf",
            resume_file_size_snapshot=2048,
        ),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(),
        None,
        SimpleNamespace(),
    )

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_details",
        new_callable=AsyncMock,
        return_value=row,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "s3_service.fetch_object_bytes",
        return_value=(b"%PDF-1.4", "application/pdf"),
    ) as fetch:
        content, filename, content_type = asyncio.run(
            JobApplicantsService.get_resume_file(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
            )
        )

    assert content == b"%PDF-1.4"
    assert filename == "alice-resume.pdf"
    assert content_type == "application/pdf"
    fetch.assert_called_once_with("resumes/candidate-1/snapshot.pdf")


def test_employer_public_profile_private_candidate_returns_clear_error():
    with patch(
        "app.service.candidate_service."
        "CandidateProfileRepo.get_candidate_detail_for_employer",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.candidate_service."
        "CandidateProfileRepo.get_candidate_profile_by_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(candidate_id="candidate-1"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                CandidateProfileService.get_candidate_detail_for_employer(
                    session=SimpleNamespace(),
                    candidate_id="candidate-1",
                )
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Candidate public profile is private or not available."
    )


def test_employer_public_profile_invalid_candidate_returns_clear_error():
    with patch(
        "app.service.candidate_service."
        "CandidateProfileRepo.get_candidate_detail_for_employer",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.candidate_service."
        "CandidateProfileRepo.get_candidate_profile_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                CandidateProfileService.get_candidate_detail_for_employer(
                    session=SimpleNamespace(),
                    candidate_id="missing-candidate",
                )
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Candidate not found."


def test_employer_public_profile_handles_non_dict_resume_sections():
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline="QA Automation Engineer",
        current_company="NMK",
        current_location="Kansas",
        total_experience=4.0,
        experience_level="Mid",
        skills_summary=None,
        work_preference="REMOTE",
        open_to_work=True,
        profile_completion_pct=85,
        active_resume_id=None,
        profile_visibility="PRIVATE",
        searchable_flag=True,
        summary="Builds reliable test suites.",
        preferred_location="Remote",
        desired_employment="FULL_TIME",
        salary_expectation=None,
        target_roles="QA Engineer",
    )
    user = SimpleNamespace(
        first_name="Sanaa",
        middle_name=None,
        last_name="Kansas",
        email="sanaa@example.com",
        mobile_number="9999999999",
        profile_image_url=None,
        cover_image_url=None,
    )
    resume_detail = SimpleNamespace(
        education_json=["bad-shape"],
        experience_json=None,
        skills_json=["Python", "Playwright"],
        certifications_json={"certifications": ["bad-shape", {"name": "ISTQB"}]},
        projects_json={"projects": [{"name": "Portal tests"}]},
        languages_json="English",
    )

    with patch(
        "app.service.candidate_service."
        "CandidateProfileRepo.get_candidate_detail_for_employer",
        new_callable=AsyncMock,
        return_value=(profile, user),
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
        new_callable=AsyncMock,
        return_value=resume_detail,
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_default_resume_for_employer_profile",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = asyncio.run(
            CandidateProfileService.get_candidate_detail_for_employer(
                session=SimpleNamespace(),
                candidate_id="candidate-1",
            )
        )

    assert result.full_name == "Sanaa Kansas"
    assert result.skills == {"skills": ["Python", "Playwright"]}
    assert result.education is None
    assert result.certifications == [{"name": "ISTQB"}]


def test_employer_public_profile_returns_complete_profile_sections_and_context():
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline="Senior Backend Engineer",
        current_company="NMK Global",
        current_location="Austin",
        total_experience=8,
        experience_level="Senior",
        skills_summary="Python, FastAPI",
        work_preference="REMOTE",
        open_to_work=True,
        profile_completion_pct=50,
        active_resume_id="resume-1",
        profile_visibility="PRIVATE",
        searchable_flag=True,
        summary="Builds APIs.",
        preferred_location="Austin, Remote",
        desired_employment="FULL_TIME",
        salary_expectation="Market",
        current_ctc=120000,
        expected_ctc=150000,
        target_roles="Backend Engineer",
        linkedin_url="https://linkedin.com/in/alice",
        github_url="https://github.com/alice",
        portfolio_url="https://alice.dev",
        website_url="https://alice.example",
    )
    user = SimpleNamespace(
        first_name="Alice",
        middle_name=None,
        last_name="Example",
        email="alice@example.com",
        mobile_number="9999999999",
        profile_image_url=None,
        cover_image_url=None,
    )
    resume_detail = SimpleNamespace(
        education_json={"education": [{"degree": "BS", "institution": "UT", "graduation_year": "2016"}]},
        experience_json={
            "experience": [
                {
                    "company": "NMK Global",
                    "role": "Lead API Engineer",
                    "employment_type": "FULL_TIME",
                    "location": "Austin",
                    "start_date": "2021-01",
                    "currently_working": True,
                    "key_highlights": "Owns platform APIs.",
                }
            ]
        },
        skills_json={"skills": [{"name": "Python", "category": "Backend"}, {"name": "python"}, {"name": "FastAPI"}]},
        certifications_json={"certifications": [{"name": "AWS"}]},
        projects_json={"projects": [{"name": "Search Platform"}]},
        languages_json={"languages": [{"name": "English"}]},
    )
    application = SimpleNamespace(
        application_id="app-1",
        job_id="job-1",
        application_status="INTERVIEW",
        applied_at=datetime(2026, 8, 1, 10, 0, 0),
    )
    interview = SimpleNamespace(status="SCHEDULED", interview_date=datetime(2026, 8, 10).date())
    resume = SimpleNamespace(
        resume_id="resume-1",
        file_name="alice.pdf",
        file_size=2048,
        uploaded_at=datetime(2026, 8, 1, 9, 0, 0),
        is_active=True,
        version_name=None,
        template=None,
    )

    with patch(
        "app.service.candidate_service.CandidateProfileRepo.get_candidate_detail_for_employer",
        new_callable=AsyncMock,
        return_value=(profile, user),
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_latest_resume_detail",
        new_callable=AsyncMock,
        return_value=resume_detail,
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_employer_candidate_context",
        new_callable=AsyncMock,
        return_value={
            "saved_candidate": True,
            "application": application,
            "interview": interview,
            "notes_count": 3,
        },
    ), patch(
        "app.service.candidate_service.CandidateProfileRepo.get_default_resume_for_employer_profile",
        new_callable=AsyncMock,
        return_value=resume,
    ):
        result = asyncio.run(
            CandidateProfileService.get_candidate_detail_for_employer(
                session=SimpleNamespace(),
                candidate_id="candidate-1",
                employer_user_id=uuid4(),
            )
        )

    assert result.current_company == "NMK Global"
    assert result.current_designation == "Lead API Engineer"
    assert result.current_employment["duration"]
    assert result.resume["preview_url"] == "/employer/job-applicants/app-1/resume/preview-file"
    assert result.resume["download_url"] == "/employer/job-applicants/app-1/resume/download-file"
    assert result.profile_completion["percentage"] > 50
    assert result.saved_candidate is True
    assert result.current_application_status == "INTERVIEW"
    assert result.interview_status == "SCHEDULED"
    assert result.notes_count == 3
    assert result.skills["categories"]["Backend"][0]["name"] == "Python"


def _compiled_sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


def test_public_candidate_listing_requires_active_candidate_and_user():
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one=lambda: 0),
                SimpleNamespace(all=lambda: []),
            ]
        )
    )

    asyncio.run(CandidateProfileRepo.list_public_candidates(session=session))

    sql = _compiled_sql(session.execute.await_args_list[0].args[0])
    assert "candidate_profiles.profile_visibility = 'PUBLIC'" in sql
    assert "candidate_profiles.status = 'ACTIVE'" in sql
    assert "users.deleted_flag IS false" in sql
    assert "users.user_status = 'ACTIVE'" in sql


def test_public_candidate_detail_requires_active_candidate_and_user():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: None))
    )

    asyncio.run(
        CandidateProfileRepo.get_public_candidate_detail(
            session=session,
            candidate_id="candidate-1",
        )
    )

    sql = _compiled_sql(session.execute.await_args.args[0])
    assert "candidate_profiles.profile_visibility = 'PUBLIC'" in sql
    assert "candidate_profiles.status = 'ACTIVE'" in sql
    assert "users.deleted_flag IS false" in sql
    assert "users.user_status = 'ACTIVE'" in sql


def test_employer_candidate_public_profile_requires_active_candidate_and_user():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: None))
    )

    asyncio.run(
        CandidateProfileRepo.get_candidate_detail_for_employer(
            session=session,
            candidate_id="candidate-1",
        )
    )

    sql = _compiled_sql(session.execute.await_args.args[0])
    assert "candidate_profiles.searchable_flag IS true" in sql
    assert "candidate_profiles.status = 'ACTIVE'" in sql
    assert "users.deleted_flag IS false" in sql
    assert "users.user_status = 'ACTIVE'" in sql
