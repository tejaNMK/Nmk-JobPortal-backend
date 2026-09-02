from app.service.candidate_job_recommendation_engine import compute_skill_match


def test_full_required_coverage_scores_high_even_missing_preferred():
    detail = compute_skill_match(
        candidate_skills={"python", "fastapi"},
        required_skills={"python", "fastapi"},
        preferred_skills={"docker", "kubernetes"},
    )

    assert detail.matched_skills == ["fastapi", "python"]
    assert detail.missing_required_skills == []
    assert detail.missing_preferred_skills == ["docker", "kubernetes"]
    assert detail.match_percentage >= 60


def test_missing_required_skills_scores_lower_than_full_coverage():
    full = compute_skill_match(
        candidate_skills={"python", "fastapi"},
        required_skills={"python", "fastapi"},
    )
    partial = compute_skill_match(
        candidate_skills={"python"},
        required_skills={"python", "fastapi"},
    )

    assert partial.missing_required_skills == ["fastapi"]
    assert partial.match_percentage < full.match_percentage


def test_no_overlap_scores_zero():
    detail = compute_skill_match(
        candidate_skills={"java", "spring"},
        required_skills={"python", "fastapi"},
    )

    assert detail.matched_skills == []
    assert detail.match_percentage == 0


def test_candidate_with_no_skills_scores_zero_not_error():
    detail = compute_skill_match(
        candidate_skills=set(),
        required_skills={"python"},
    )

    assert detail.match_percentage == 0
    assert detail.missing_required_skills == ["python"]


def test_job_with_no_listed_skills_is_neutral_not_penalized():
    detail = compute_skill_match(
        candidate_skills={"python"},
        required_skills=set(),
        preferred_skills=set(),
    )

    assert detail.match_percentage == 50.0


def test_extra_candidate_skills_are_reported_separately():
    detail = compute_skill_match(
        candidate_skills={"python", "docker", "aws"},
        required_skills={"python"},
    )

    assert detail.extra_skills == ["aws", "docker"]
    assert detail.matched_skills == ["python"]