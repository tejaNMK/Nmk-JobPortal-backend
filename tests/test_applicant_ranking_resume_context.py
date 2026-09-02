from types import SimpleNamespace

from app.service.employer_service.applicant_ranking_service import (
    ApplicantRankingService,
    _resume_semantic_context,
)


def test_resume_semantic_context_uses_all_parsed_sections_and_drops_private_fields():
    resume_detail = SimpleNamespace(
        skills_json={"skills": [{"name": "Python"}, {"name": "FastAPI"}]},
        experience_json={
            "experience": [
                {
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "description": "Built APIs.",
                    "email": "private@example.test",
                    "phone": "9999999999",
                }
            ]
        },
        education_json={"education": [{"degree": "B.Tech", "institution": "NMK"}]},
        certifications_json={"certifications": [{"name": "AWS Cloud Practitioner"}]},
        projects_json={"projects": [{"name": "Hiring API", "technologies": ["Python"]}]},
        languages_json={"languages": [{"name": "English"}, {"name": "Hindi"}]},
        generated_at=None,
    )

    context = _resume_semantic_context(resume_detail)

    assert context.metadata["resume_context_used"] is True
    assert context.metadata["resume_sections_used"] == [
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
        "languages",
    ]
    serialized = str(context.data)
    assert "private@example.test" not in serialized
    assert "9999999999" not in serialized
    assert "Hiring API" in serialized
    assert "AWS Cloud Practitioner" in serialized


def test_semantic_prompt_contains_resume_context_and_metadata():
    profile = SimpleNamespace(
        headline="Backend Engineer",
        summary="Builds APIs",
        total_experience=4,
        current_location="Bengaluru",
        preferred_location="Remote",
        work_preference="REMOTE",
        desired_employment="FULL_TIME",
        skills_summary="Python, FastAPI",
        target_roles="Backend Engineer",
        expected_ctc=None,
        profile_completion_pct=80,
    )
    job = SimpleNamespace(
        title="Senior Backend Engineer",
        description="Build APIs with Python.",
        skills=[SimpleNamespace(skill="Python")],
        requirements=["FastAPI"],
        responsibilities=["Design APIs"],
        experience_min=3,
        experience_max=6,
        education="B.Tech",
        location="Remote",
        work_mode="REMOTE",
        employment_type="FULL_TIME",
    )
    resume_detail = SimpleNamespace(
        skills_json={"skills": ["Python"]},
        experience_json={"experience": [{"title": "Backend Engineer"}]},
        education_json=None,
        certifications_json=None,
        projects_json={"projects": [{"name": "API Platform"}]},
        languages_json=None,
        generated_at=None,
    )

    prompt, metadata = ApplicantRankingService._semantic_prompt(
        profile,
        job,
        resume_detail,
    )

    assert "resume_context" in prompt
    assert "API Platform" in prompt
    assert metadata["resume_context_used"] is True
    assert "projects" in metadata["resume_sections_used"]
