from __future__ import annotations

import pytest

from app.schema.candidate_job_search import CandidateJobSearchQuery


@pytest.mark.parametrize(
    "raw, expected",
    [
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
        (5, 5),
        (8, 8),
        (12, 12),
        (20, 20),
    ],
)
def test_numeric_experience_accepts_non_negative(raw, expected):
    q = CandidateJobSearchQuery(experience=raw)
    assert q.experience == expected


@pytest.mark.parametrize("raw", [-1, "abc", "unknown", None])
def test_numeric_experience_invalid(raw):
    if raw is None:
        # None is allowed (means filter omitted)
        q = CandidateJobSearchQuery(experience=None)
        assert q.experience is None
        return

    with pytest.raises(ValueError):
        CandidateJobSearchQuery(experience=raw)


def test_backward_compat_experience_level_still_valid():
    q = CandidateJobSearchQuery(experience_level="1-3 Years")
    assert q.experience_level == "1-3 Years"


def test_experience_precedence_numeric_over_legacy():
    q = CandidateJobSearchQuery(experience=4, experience_level="5+ Years")
    assert q.experience == 4
    assert q.experience_level == "5+ Years"

