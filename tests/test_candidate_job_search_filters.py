import pytest

from fastapi import HTTPException

from app.repository.candidate_repository.candidate_job_search_repo import CandidateJobSearchRepo
from app.schema.candidate_job_search import CandidateJobSearchQuery
from app.service.candidate_job_search_service import CandidateJobSearchService


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("REMOTE", "Remote"),
        ("remote", "Remote"),
        ("remote-work", "Remote"),
        ("remote_work", "Remote"),
        ("ON_SITE", "Onsite"),
        ("on-site", "Onsite"),
        ("onsite", "Onsite"),
        ("HYBRID", "Hybrid"),
        ("hybrid", "Hybrid"),
    ],
)
def test_work_preference_normalization(raw, expected):
    q = CandidateJobSearchQuery(work_preference=raw)
    assert q.work_preference == expected


@pytest.mark.parametrize("raw", ["office", "random"])
def test_work_preference_invalid_400(raw):
    with pytest.raises(ValueError):
        CandidateJobSearchQuery(work_preference=raw)


def test_work_preference_blank_is_ignored():
    q = CandidateJobSearchQuery(work_preference="")
    assert q.work_preference is None



@pytest.mark.parametrize("raw", [-1, -10, "abc", "unknown"])
def test_experience_validation_errors(raw):
    with pytest.raises(ValueError):
        CandidateJobSearchQuery(experience=raw)


def test_experience_level_legacy_normalization():
    q = CandidateJobSearchQuery(experience_level="1-3 years")
    assert q.experience_level == "1-3 Years"


def test_experience_precedence_numeric():
    q = CandidateJobSearchQuery(experience=3, experience_level="5+ Years")
    assert q.experience == 3
    assert q.experience_level == "5+ Years"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("24h", "24h"),
        ("24H", "24h"),
        ("7days", "7d"),
        ("30D", "30d"),
    ],
)
def test_posted_within_normalization(raw, expected):
    q = CandidateJobSearchQuery(posted_within=raw)
    assert q.posted_within == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Newest", "Newest"),
        ("newest", "Newest"),
        ("relevance", "Relevance"),
    ],
)
def test_sort_normalization(raw, expected):
    q = CandidateJobSearchQuery(sort=raw)
    assert q.sort == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Remote", "REMOTE"),
        ("remote", "REMOTE"),
        ("Remote Work", "REMOTE"),
        ("Onsite", "ONSITE"),
        ("on-site", "ONSITE"),
        ("Hybrid", "HYBRID"),
    ],
)
def test_repo_normalizes_work_preference_for_db_query(raw, expected):
    assert CandidateJobSearchRepo._normalize_work_preference_for_query(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("full-time", "FULL_TIME"),
        ("Full Time", "FULL_TIME"),
        ("part-time", "PART_TIME"),
        ("Part Time", "PART_TIME"),
        ("contract", "CONTRACT"),
        ("internship", "INTERNSHIP"),
    ],
)
def test_repo_normalizes_employment_type_for_db_query(raw, expected):
    assert CandidateJobSearchRepo._normalize_employment_type_for_query(raw) == expected


def test_job_description_preview_is_limited_to_120_chars():
    description = "a" * 121

    preview = CandidateJobSearchService._job_description_preview(description)

    assert preview == "a" * 120
    assert len(preview) == 120

