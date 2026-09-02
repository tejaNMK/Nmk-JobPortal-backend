import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schema.invitations import CandidateSearchRequest
from app.service.employer_service.candidate_search_service import (
    EmployerCandidateSearchService,
)


def test_employer_candidate_search_separates_company_and_designation():
    candidate_user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline="Backend specialist",
        current_company="NMK Global",
        total_experience=7,
        current_location="Remote",
        skills_summary="Python, FastAPI, Python",
        notice_period="30 days",
        profile_completion_pct=90,
        active_resume_id="resume-1",
        open_to_work=True,
        salary_expectation="150000",
        updated_at=datetime(2026, 8, 1, 12, 0, 0),
    )
    user = SimpleNamespace(
        first_name="Alice",
        middle_name=None,
        last_name="Example",
        profile_image_url=f"profile-images/{candidate_user_id}/profile.jpg",
    )
    resume_detail = SimpleNamespace(
        skills_json={"skills": [{"name": "Python"}, {"name": "python"}, {"name": "FastAPI"}]},
        education_json={"education": [{"degree": "BS", "institution": "UT"}]},
        experience_json={
            "experience": [
                {
                    "company": "NMK Global",
                    "role": "Lead API Engineer",
                    "currently_working": True,
                }
            ]
        },
    )

    with patch(
        "app.service.employer_service.candidate_search_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.candidate_search_service.EmployerCandidateSearchRepository.search_candidates",
        new_callable=AsyncMock,
        return_value=(1, [(profile, user, resume_detail)]),
    ):
        result = asyncio.run(
            EmployerCandidateSearchService.search_candidates(
                session=SimpleNamespace(),
                payload={"user_id": "11111111-1111-1111-1111-111111111111"},
                filters=CandidateSearchRequest(),
            )
        )

    item = result.items[0]
    assert item.current_company == "NMK Global"
    assert item.current_designation == "Lead API Engineer"
    assert item.profile_photo == f"/profile-images/{candidate_user_id}/profile.jpg"
    assert item.experience == 7
    assert item.highest_education == "BS, UT"
    assert item.top_skills == ["Python", "FastAPI"]
    assert item.resume_available is True
    assert item.open_to_work is True
    assert item.expected_salary == "150000"
    assert item.notice_period == "30 days"
