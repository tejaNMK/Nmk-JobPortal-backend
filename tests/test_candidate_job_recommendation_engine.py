from app.service.candidate_job_recommendation_engine import (
    CandidateMatchContext,
    JobMatchContext,
    rank_jobs_for_candidate,
    score_job_for_candidate,
)


def _candidate(**overrides) -> CandidateMatchContext:
    defaults = dict(
        skills={"python", "fastapi", "postgresql"},
        total_experience_years=4,
        headline="Senior Backend Engineer",
        preferred_titles={"Backend Engineer"},
        current_location="Bangalore",
        preferred_location="Bangalore",
        desired_employment_type="FULL_TIME",
        work_preference="REMOTE",
        expected_salary_min=80000,
        expected_salary_max=120000,
        profile_completion_pct=90,
    )
    defaults.update(overrides)
    return CandidateMatchContext(**defaults)


def _job(**overrides) -> JobMatchContext:
    defaults = dict(
        job_id="job-1",
        title="Backend Engineer",
        required_skills={"python", "fastapi"},
        experience_min=3,
        experience_max=6,
        location="Bangalore",
        employment_type="FULL_TIME",
        work_mode="REMOTE",
        salary_min=90000,
        salary_max=110000,
    )
    defaults.update(overrides)
    return JobMatchContext(**defaults)


def test_strong_match_scores_high_and_explains_why():
    result = score_job_for_candidate(_candidate(), _job())

    assert result.score >= 90
    assert any("skill" in r.lower() for r in result.reasons)
    assert any("experience" in r.lower() for r in result.reasons)


def test_poor_match_scores_low():
    candidate = _candidate()
    job = _job(
        job_id="job-2",
        title="Frontend Designer",
        required_skills={"figma", "css"},
        experience_min=0,
        experience_max=2,
        location="Delhi",
        employment_type="INTERNSHIP",
        work_mode="ONSITE",
        salary_min=10000,
        salary_max=20000,
    )

    result = score_job_for_candidate(candidate, job)

    assert result.score < 30


def test_no_matching_skills_still_scores_other_factors():
    candidate = _candidate(skills={"java", "spring"})
    job = _job()

    result = score_job_for_candidate(candidate, job)

    assert result.score > 0
    assert result.breakdown["skills"] == 0


def test_job_with_no_listed_skills_is_not_penalized():
    candidate = _candidate()
    job = _job(required_skills=set())

    result = score_job_for_candidate(candidate, job)

    assert result.breakdown["skills"] > 0


def test_rank_jobs_orders_best_match_first_and_filters_low_scores():
    candidate = _candidate()
    strong = _job(job_id="strong")
    weak = _job(
        job_id="weak",
        title="Frontend Designer",
        required_skills={"figma"},
        experience_min=0,
        experience_max=1,
        location="Delhi",
        employment_type="INTERNSHIP",
        work_mode="ONSITE",
        salary_min=5000,
        salary_max=8000,
    )

    ranked = rank_jobs_for_candidate(candidate, [weak, strong])

    assert [r.job_id for r in ranked] == ["strong"]


def test_rank_jobs_breaks_ties_deterministically_by_job_id():
    candidate = _candidate()
    job_a = _job(job_id="job-b")
    job_b = _job(job_id="job-a")

    ranked = rank_jobs_for_candidate(candidate, [job_a, job_b])

    assert [r.job_id for r in ranked] == ["job-a", "job-b"]


def test_experience_outside_range_but_close_gets_partial_credit():
    candidate = _candidate(total_experience_years=7)
    job = _job(experience_min=3, experience_max=6)

    result = score_job_for_candidate(candidate, job)

    assert 0 < result.breakdown["experience"] < 15


def test_missing_candidate_signals_do_not_crash_and_stay_neutral():
    candidate = CandidateMatchContext()
    job = _job()

    result = score_job_for_candidate(candidate, job)

    assert 0 <= result.score <= 100