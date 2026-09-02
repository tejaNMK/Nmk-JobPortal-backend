from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.schema.job import CloseJobRequest
from app.service.employer_service.job_service import JobService


def test_close_own_job():
    open_job = SimpleNamespace(job_id="job-1", employer_id="emp-1", status="PUBLISHED")
    closed_job = SimpleNamespace(
        job_id="job-1",
        employer_id="emp-1",
        status="CLOSED",
        closed_at=datetime.now(UTC),
        closed_reason="Position Filled",
    )

    with patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=open_job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.close_job",
        new_callable=AsyncMock,
        return_value=closed_job,
    ) as close_job:
        result = asyncio.run(
            JobService.close_job(
                session=None,
                employer_id="emp-1",
                job_id="job-1",
                request=CloseJobRequest(reason="Position Filled"),
                actor_user_id="user-1",
                actor_email="hr@example.com",
            )
        )

    assert result.status == "CLOSED"
    assert result.closed_reason == "Position Filled"
    close_job.assert_awaited_once()


def test_close_another_employers_job_returns_403():
    job = SimpleNamespace(job_id="job-1", employer_id="emp-2", status="PUBLISHED")

    with patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.close_job",
        new_callable=AsyncMock,
    ) as close_job:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.close_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="job-1",
                    request=CloseJobRequest(reason=None),
                    actor_user_id=None,
                    actor_email=None,
                )
            )

    assert exc.value.status_code == 403
    close_job.assert_not_called()


def test_close_already_closed_job_returns_409():
    job = SimpleNamespace(job_id="job-1", employer_id="emp-1", status="CLOSED")

    with patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.close_job",
        new_callable=AsyncMock,
    ) as close_job:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.close_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="job-1",
                    request=CloseJobRequest(reason=None),
                    actor_user_id=None,
                    actor_email=None,
                )
            )

    assert exc.value.status_code == 409
    close_job.assert_not_called()


def test_close_invalid_job_returns_404():
    with patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.close_job",
        new_callable=AsyncMock,
    ) as close_job:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.close_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="missing",
                    request=CloseJobRequest(reason=None),
                    actor_user_id=None,
                    actor_email=None,
                )
            )

    assert exc.value.status_code == 404
    close_job.assert_not_called()


def test_close_draft_job_returns_400():
    job = SimpleNamespace(job_id="job-1", employer_id="emp-1", status="DRAFT")

    with patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.close_job",
        new_callable=AsyncMock,
    ) as close_job:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.close_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="job-1",
                    request=CloseJobRequest(reason=None),
                    actor_user_id=None,
                    actor_email=None,
                )
            )

    assert exc.value.status_code == 400
    close_job.assert_not_called()
