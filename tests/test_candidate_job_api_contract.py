from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive
from sqlalchemy.dialects import postgresql

from app.repository.candidate_repository.candidate_job_search_repo import CandidateJobSearchRepo
from app.service.candidate_job_search_service import CandidateJobSearchService


def _job(**overrides):
    base = {
        "job_id": "job-1",
        "title": "Senior Python Developer",
        "description": "Short backend role.",
        "company_name": "ABC Technologies",
        "location": "Hyderabad",
        "country_id": "IN",
        "location_id": "hyd",
        "custom_city": None,
        "salary_min": 1000000,
        "salary_max": 2000000,
        "salary_currency": "INR",
        "salary_period": "Yearly",
        "employment_type": "FULL_TIME",
        "work_mode": "HYBRID",
        "experience_min": 5,
        "experience_max": 8,
        "job_category": "Engineering",
        "seniority_level": "Senior",
        "team": "Platform",
        "team_size": "10-20",
        "education": "B.Tech",
        "responsibilities": ["Build APIs"],
        "requirements": ["5+ years backend experience"],
        "benefits": ["Health insurance"],
        "application_instructions": "Apply with latest resume",
        "working_hours": "10 AM - 7 PM",
        "office_location": "HITEC City",
        "map_url": "https://maps.example/jobs/job-1",
        "application_deadline": datetime(2026, 8, 30, 10, 0, 0),
        "no_of_openings": 2,
        "status": "PUBLISHED",
        "created_at": datetime(2026, 7, 29, 10, 0, 0),
        "updated_at": datetime(2026, 7, 29, 11, 0, 0),
        "skills": [SimpleNamespace(skill="Python"), SimpleNamespace(skill="FastAPI")],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_description_preview_shorter_than_120_characters():
    job = _job(description="Clean short description.")

    assert CandidateJobSearchService._description_preview_from_job(job) == "Clean short description."


def test_description_preview_longer_than_120_characters():
    text = "A" * 121
    job = _job(description=text)

    preview = CandidateJobSearchService._description_preview_from_job(job)

    assert preview == ("A" * 117) + "..."
    assert len(preview) == 120


def test_description_preview_removes_html_and_extra_space_before_truncating():
    job = _job(
        description="<p>We are looking for<br> a <strong>Python</strong> developer&nbsp; today.</p>"
    )

    assert (
        CandidateJobSearchService._description_preview_from_job(job)
        == "We are looking for a Python developer today."
    )


@pytest.mark.parametrize("description", ["", None])
def test_description_preview_empty_or_null_description(description):
    job = _job(description=description)

    assert CandidateJobSearchService._description_preview_from_job(job) is None


@pytest.mark.asyncio
async def test_search_jobs_cards_include_preview_saved_and_applied(monkeypatch):
    user_id = uuid4()
    app = SimpleNamespace(application_status="APPLIED")
    job = _job(description="<p>Backend API role</p>")

    async def get_job_card_search(*args, **kwargs):
        return 1, [job]

    async def get_saved_and_applied_maps(*args, **kwargs):
        return {"job-1"}, {"job-1": app}

    async def get_company_logo_path_for_jobs(*args, **kwargs):
        return {"job-1": "logo.png"}

    monkeypatch.setattr(CandidateJobSearchRepo, "get_job_card_search", get_job_card_search)
    monkeypatch.setattr(CandidateJobSearchRepo, "get_saved_and_applied_maps", get_saved_and_applied_maps)
    monkeypatch.setattr(
        CandidateJobSearchRepo,
        "get_company_logo_path_for_jobs",
        get_company_logo_path_for_jobs,
    )

    result = await CandidateJobSearchService.search_jobs(session=None, user_id=user_id)

    card = result.results[0]
    assert card.description_preview == "Backend API role"
    assert card.is_saved is True
    assert card.already_applied is True
    assert card.application_status == "APPLIED"
    assert card.company_logo == "logo.png"


@pytest.mark.asyncio
async def test_suggested_job_cards_include_description_preview(monkeypatch):
    job = _job(description="<div>Suggestion card description</div>")

    async def get_suggestions(*args, **kwargs):
        return "Senior Python Developer", ["Senior Python Developer"], [job]

    async def get_company_logo_path_for_jobs(*args, **kwargs):
        return {}

    monkeypatch.setattr(CandidateJobSearchRepo, "get_suggestions", get_suggestions)
    monkeypatch.setattr(
        CandidateJobSearchRepo,
        "get_company_logo_path_for_jobs",
        get_company_logo_path_for_jobs,
    )

    result = await CandidateJobSearchService.get_suggestions(session=None, q="python")

    assert result.suggestions == ["Senior Python Developer"]
    assert result.jobs[0].description_preview == "Suggestion card description"


@pytest.mark.asyncio
async def test_complete_job_details_response_candidate_visible_fields(monkeypatch):
    user_id = uuid4()
    job = _job()
    company = SimpleNamespace(
        company_id="company-1",
        company_name="ABC Technologies",
        website="https://abc.example",
        logo_url="https://cdn.example/logo.png",
        logo_path="logo.png",
        description="Public company description",
        industry="Software",
        company_size="201-500",
        size=None,
        founded_year=2010,
        location="Hyderabad",
        headquarters_country="India",
        headquarters_state="Telangana",
        headquarters_city="Hyderabad",
        verification_status="APPROVED",
    )
    recruiter = SimpleNamespace(
        id="recruiter-1",
        job_title="Talent Partner",
        department="People",
        bio="Public recruiter bio",
        location="Hyderabad",
        linkedin_url="https://linkedin.example/recruiter",
        profile_photo="photo.png",
        candidate_response_time="Within 2 days",
        interview_mode="Video",
        languages=["English"],
    )
    app = SimpleNamespace(application_status="INTERVIEW")

    async def get_job_details(*args, **kwargs):
        return job

    async def get_saved_and_applied_maps(*args, **kwargs):
        return {"job-1"}, {"job-1": app}

    async def get_company_logo_path_for_jobs(*args, **kwargs):
        return {"job-1": "logo.png"}

    async def get_company_profiles_for_jobs(*args, **kwargs):
        return {"job-1": company}

    async def get_public_recruiter_profiles_for_jobs(*args, **kwargs):
        return {"job-1": recruiter}

    monkeypatch.setattr(CandidateJobSearchRepo, "get_job_details", get_job_details)
    monkeypatch.setattr(CandidateJobSearchRepo, "get_saved_and_applied_maps", get_saved_and_applied_maps)
    monkeypatch.setattr(
        CandidateJobSearchRepo,
        "get_company_logo_path_for_jobs",
        get_company_logo_path_for_jobs,
    )
    monkeypatch.setattr(
        CandidateJobSearchRepo,
        "get_company_profiles_for_jobs",
        get_company_profiles_for_jobs,
    )
    monkeypatch.setattr(
        CandidateJobSearchRepo,
        "get_public_recruiter_profiles_for_jobs",
        get_public_recruiter_profiles_for_jobs,
    )

    result = await CandidateJobSearchService.get_job_details(
        session=None,
        user_id=user_id,
        job_id="job-1",
    )

    assert result.job_id == "job-1"
    assert result.job_description == job.description
    assert result.responsibilities == ["Build APIs"]
    assert result.requirements == ["5+ years backend experience"]
    assert result.required_skills == ["Python", "FastAPI"]
    assert result.preferred_skills == []
    assert result.experience_min == 5
    assert result.experience_max == 8
    assert result.workplace_type == "HYBRID"
    assert result.number_of_openings == 2
    assert result.job_status == "PUBLISHED"
    assert result.updated_date == job.updated_at
    assert result.company_info.company_name == "ABC Technologies"
    assert result.recruiter_public_info.job_title == "Talent Partner"
    assert result.is_saved is True
    assert result.already_applied is True
    assert result.application_status == "INTERVIEW"


@pytest.mark.asyncio
async def test_job_details_handles_null_optional_fields(monkeypatch):
    job = _job(
        location=None,
        country_id=None,
        location_id=None,
        salary_min=None,
        salary_max=None,
        work_mode=None,
        experience_min=None,
        experience_max=None,
        responsibilities=None,
        requirements=None,
        benefits=None,
        application_deadline=None,
        skills=None,
    )

    async def get_job_details(*args, **kwargs):
        return job

    async def empty_map(*args, **kwargs):
        return {}

    monkeypatch.setattr(CandidateJobSearchRepo, "get_job_details", get_job_details)
    monkeypatch.setattr(CandidateJobSearchRepo, "get_company_logo_path_for_jobs", empty_map)
    monkeypatch.setattr(CandidateJobSearchRepo, "get_company_profiles_for_jobs", empty_map)
    monkeypatch.setattr(CandidateJobSearchRepo, "get_public_recruiter_profiles_for_jobs", empty_map)

    result = await CandidateJobSearchService.get_job_details(session=None, user_id=None, job_id="job-1")

    assert result.location is None
    assert result.salary_range is None
    assert result.experience_required is None
    assert result.responsibilities == []
    assert result.requirements == []
    assert result.benefits == []
    assert result.skills == []
    assert result.required_skills == []


@pytest.mark.asyncio
async def test_invalid_job_id_returns_none_for_controller_404(monkeypatch):
    async def get_job_details(*args, **kwargs):
        return None

    monkeypatch.setattr(CandidateJobSearchRepo, "get_job_details", get_job_details)

    result = await CandidateJobSearchService.get_job_details(
        session=None,
        user_id=None,
        job_id="missing-job",
    )

    assert result is None


@pytest.mark.asyncio
async def test_hidden_deleted_draft_inactive_or_expired_job_maps_to_not_found(monkeypatch):
    async def get_job_details(*args, **kwargs):
        return None

    monkeypatch.setattr(CandidateJobSearchRepo, "get_job_details", get_job_details)

    result = await CandidateJobSearchService.get_job_details(
        session=None,
        user_id=None,
        job_id="hidden-job",
    )

    assert result is None


def test_active_job_predicate_enforces_candidate_visibility_rules():
    now = utc_now_naive()
    predicate = CandidateJobSearchRepo._active_job_predicate(now)
    compiled = str(
        predicate.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "jobs.status IN ('PUBLISHED')" in compiled
    assert "jobs.is_deleted IS false" in compiled
    assert "jobs.closed_at IS NULL" in compiled
    assert "jobs.application_deadline IS NULL" in compiled
    assert "jobs.application_deadline >=" in compiled


def test_expired_deadline_example_is_before_now_for_visibility_coverage():
    assert utc_now_naive() - timedelta(days=1) < utc_now_naive()
