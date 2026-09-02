from app.service.employer_service.ai_candidate_matching_engine import (
    CandidateMatchInput,
    JobMatchInput,
    match_level,
    score_candidate_for_job,
)


def _job():
    return JobMatchInput(
        job_id="job-1",
        title="Senior Python Backend Engineer",
        description="Build FastAPI services on PostgreSQL and AWS.",
        required_skills={"python", "fastapi", "postgresql", "aws"},
        preferred_skills={"docker"},
        experience_min=3,
        experience_max=8,
        education="Bachelor Computer Science",
        location="Hyderabad",
        work_mode="HYBRID",
        employment_type="FULL_TIME",
        industry="Healthcare",
    )


def test_perfect_candidate_scores_excellent_match():
    candidate = CandidateMatchInput(
        candidate_id="cand-1",
        candidate_name="Asha Rao",
        skills={"python", "fastapi", "postgresql", "aws", "docker"},
        total_experience_years=5,
        headline="Senior Python Backend Engineer",
        summary="Healthcare API engineer using Python, FastAPI, PostgreSQL, AWS, and Docker.",
        target_roles="Senior Python Backend Engineer",
        job_titles=["Senior Python Backend Engineer"],
        current_location="Hyderabad",
        preferred_location="Hyderabad",
        education=["Bachelor Computer Science"],
    )

    result = score_candidate_for_job(candidate, _job())

    assert result.overall_score >= 90
    assert match_level(result.overall_score) == "Excellent Match"
    assert result.missing_required_skills == []
    assert result.recommendation == "Highly Recommended"


def test_candidate_missing_one_required_skill_is_penalized_but_not_rejected():
    candidate = CandidateMatchInput(
        candidate_id="cand-2",
        candidate_name="Dev Iyer",
        skills={"python", "fastapi", "postgresql"},
        total_experience_years=5,
        headline="Python Backend Engineer",
        current_location="Hyderabad",
    )

    result = score_candidate_for_job(candidate, _job())

    assert "aws" in result.missing_required_skills
    assert result.overall_score < 90
    assert result.overall_score >= 60
    assert result.recommendation == "Review Manually"


def test_candidate_below_minimum_experience_keeps_skill_signal():
    candidate = CandidateMatchInput(
        candidate_id="cand-3",
        candidate_name="Junior Dev",
        skills={"python", "fastapi", "postgresql", "aws"},
        total_experience_years=1,
        headline="Python Backend Engineer",
        current_location="Hyderabad",
    )

    result = score_candidate_for_job(candidate, _job())

    assert result.skills_score == 35
    assert result.experience_score < 25
    assert "Experience is below" in " ".join(result.gaps)


def test_synonymous_skills_match_required_skill():
    candidate = CandidateMatchInput(
        candidate_id="cand-4",
        candidate_name="Synonym Dev",
        skills={"py", "fastapi", "postgres", "amazonwebservices"},
        total_experience_years=4,
        headline="Backend Engineer",
        current_location="Hyderabad",
    )
    job = _job()

    from app.service.employer_service.ai_candidate_matching_engine import normalize_skills

    candidate.skills = normalize_skills(candidate.skills)
    job.required_skills = normalize_skills(job.required_skills)
    result = score_candidate_for_job(candidate, job)

    assert result.missing_required_skills == []
    assert {"python", "postgresql", "aws"}.issubset(set(result.matched_skills))
