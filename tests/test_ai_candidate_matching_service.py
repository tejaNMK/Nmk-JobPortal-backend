from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from app.schema.employer_ai_candidate_matching import AICandidateMatchRunRequest
from app.service.employer_service.ai_candidate_matching_service import (
    AICandidateMatchingService,
    _is_stale,
)


class FakeSession:
    pass


def _payload(user_id=None):
    return {"user_id": str(user_id or uuid4()), "email": "hr@example.com"}


def test_matching_request_defaults_to_applicants_scope():
    assert AICandidateMatchRunRequest().scope == "applicants"


def test_stale_detection_tracks_scoring_job_candidate_and_resume_changes():
    now = datetime.now(UTC).replace(tzinfo=None)
    match = SimpleNamespace(
        scoring_version="ai_candidate_matching_v1",
        job_updated_at=now,
        candidate_updated_at=now,
        resume_generated_at=now,
    )

    assert not _is_stale(
        match,
        SimpleNamespace(updated_at=now),
        SimpleNamespace(updated_at=now),
        SimpleNamespace(generated_at=now),
    )
    assert _is_stale(
        match,
        SimpleNamespace(updated_at=now),
        SimpleNamespace(updated_at=now + timedelta(seconds=1)),
        SimpleNamespace(generated_at=now),
    )
    assert _is_stale(
        match,
        SimpleNamespace(updated_at=now + timedelta(seconds=1)),
        SimpleNamespace(updated_at=now),
        SimpleNamespace(generated_at=now),
    )
    assert _is_stale(
        match,
        SimpleNamespace(updated_at=now),
        SimpleNamespace(updated_at=now),
        SimpleNamespace(generated_at=now + timedelta(seconds=1)),
    )
    match.scoring_version = "old"
    assert _is_stale(
        match,
        SimpleNamespace(updated_at=now),
        SimpleNamespace(updated_at=now),
        SimpleNamespace(generated_at=now),
    )


@pytest.mark.asyncio
async def test_generate_matches_rejects_employer_without_profile():
    with patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_employer_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await AICandidateMatchingService.generate_matches(
                session=FakeSession(),
                payload=_payload(),
                job_id="job-1",
                request=AICandidateMatchRunRequest(),
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Employer profile not found"


@pytest.mark.asyncio
async def test_generate_matches_rejects_other_employers_job():
    with patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_employer_id",
        new=AsyncMock(return_value="emp-1"),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingService._enforce_subscription",
        new=AsyncMock(),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_owned_job",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await AICandidateMatchingService.generate_matches(
                session=FakeSession(),
                payload=_payload(),
                job_id="job-1",
                request=AICandidateMatchRunRequest(),
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job not found"


@pytest.mark.asyncio
async def test_subscription_feature_disabled_blocks_matching():
    with patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_employer_id",
        new=AsyncMock(return_value="emp-1"),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.SubscriptionValidator.require_feature",
        new=AsyncMock(side_effect=HTTPException(status_code=403, detail="disabled")),
    ):
        with pytest.raises(HTTPException) as exc:
            await AICandidateMatchingService.generate_matches(
                session=FakeSession(),
                payload=_payload(),
                job_id="job-1",
                request=AICandidateMatchRunRequest(),
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == "disabled"


@pytest.mark.asyncio
async def test_no_eligible_candidates_returns_empty_result_without_usage_increment():
    job = SimpleNamespace(
        job_id="job-1",
        description="Backend role",
        skills=[],
        requirements=[],
    )
    with patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_employer_id",
        new=AsyncMock(return_value="emp-1"),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingService._enforce_subscription",
        new=AsyncMock(),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_owned_job",
        new=AsyncMock(return_value=job),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.AICandidateMatchingRepository.get_candidate_pool",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.service.employer_service.ai_candidate_matching_service.UserSubscriptionRepository.increment_usage",
        new=AsyncMock(),
    ) as increment_usage:
        result = await AICandidateMatchingService.generate_matches(
            session=FakeSession(),
            payload=_payload(),
            job_id="job-1",
            request=AICandidateMatchRunRequest(),
        )

    assert result.total_candidates_considered == 0
    assert result.total_matches_generated == 0
    increment_usage.assert_not_awaited()
