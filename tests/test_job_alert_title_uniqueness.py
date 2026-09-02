from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.candidate_schema import JobAlertUpdateSchema, JobAlertUpsertSchema
from app.repository.candidate_repo import CandidateProfileRepo
from app.service.candidate_service import (
    CandidateProfileService,
    JOB_ALERT_TITLE_DUPLICATE_MESSAGE,
)


def _valid_payload(**overrides):
    payload = {
        "title": "Alert1",
        "job_category": "Engineering",
        "job_title": "Backend Engineer",
        "preferred_location": "Hyderabad",
        "experience_level": "MID_LEVEL",
        "employment_type": "FULL_TIME",
        "notification_preference": "EMAIL",
        "frequency": "DAILY",
    }
    payload.update(overrides)
    return payload


def _alert(**overrides):
    data = {
        "alert_id": "alert-1",
        "candidate_id": "candidate-1",
        "title": "Alert1",
        "job_category": "Engineering",
        "job_title": "Backend Engineer",
        "preferred_location": "Hyderabad",
        "experience_level": "MID_LEVEL",
        "employment_type": "FULL_TIME",
        "notification_preference": "EMAIL",
        "frequency": "DAILY",
        "timezone": "UTC",
        "is_active": True,
        "created_at": datetime(2026, 8, 6, 10, 0),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class _AllowingSubscriptionValidator:
    def __init__(self, *args, **kwargs):
        pass

    async def require_feature(self, feature_name):
        return None

    async def get_limit(self, limit_name):
        return None


def _service_patches(
    *,
    candidate_id="candidate-1",
    existing_alert=None,
    title_duplicate=None,
    criteria_duplicate=None,
    created_alert=None,
    updated_alert=None,
):
    return (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(candidate_id=candidate_id),
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator",
            _AllowingSubscriptionValidator,
        ),
        patch(
            "app.service.candidate_service.MasterDataService.validate_job_category",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_job_alert",
            new_callable=AsyncMock,
            return_value=existing_alert,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
            new_callable=AsyncMock,
            return_value=title_duplicate,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_duplicate_job_alert",
            new_callable=AsyncMock,
            return_value=criteria_duplicate,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.create_job_alert",
            new_callable=AsyncMock,
            return_value=created_alert or _alert(candidate_id=candidate_id),
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_job_alert",
            new_callable=AsyncMock,
            return_value=updated_alert or _alert(candidate_id=candidate_id),
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    )


@pytest.mark.asyncio
async def test_create_job_alert_rejects_duplicate_title_with_different_criteria():
    patches = _service_patches(
        title_duplicate=_alert(alert_id="existing-alert"),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as create_alert, patches[7], patches[8]:
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.create_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                data=JobAlertUpsertSchema(
                    **_valid_payload(
                        experience_level="SENIOR",
                        employment_type="CONTRACT",
                        notification_preference="BOTH",
                    )
                ),
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == JOB_ALERT_TITLE_DUPLICATE_MESSAGE
    create_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_alert_duplicate_title_check_uses_trimmed_title():
    find_by_title = AsyncMock(return_value=_alert(alert_id="existing-alert"))
    patches = _service_patches()

    with patches[0], patches[1], patches[2], patches[3], patch(
        "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
        find_by_title,
    ), patches[5], patches[6], patches[7], patches[8]:
        with pytest.raises(HTTPException):
            await CandidateProfileService.create_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                data=JobAlertUpsertSchema(**_valid_payload(title="  Alert1  ")),
            )

    assert find_by_title.await_args.kwargs["title"] == "Alert1"


@pytest.mark.asyncio
async def test_update_job_alert_rejects_renaming_to_existing_title():
    existing_alert = _alert(alert_id="alert-2", title="Different")
    patches = _service_patches(
        existing_alert=existing_alert,
        title_duplicate=_alert(alert_id="alert-1", title="Alert1"),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7] as update_alert, patches[8]:
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.update_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                alert_id="alert-2",
                data=JobAlertUpdateSchema(title="Alert1"),
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == JOB_ALERT_TITLE_DUPLICATE_MESSAGE
    update_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_job_alert_without_changing_own_title_succeeds():
    existing_alert = _alert(alert_id="alert-1", title="Alert1")
    updated_alert = _alert(alert_id="alert-1", title="Alert1", frequency="WEEKLY")
    find_by_title = AsyncMock(return_value=None)
    patches = _service_patches(
        existing_alert=existing_alert,
        updated_alert=updated_alert,
    )

    with patches[0], patches[1], patches[2], patches[3], patch(
        "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
        find_by_title,
    ), patches[5], patches[6], patches[7] as update_alert, patches[8]:
        result = await CandidateProfileService.update_job_alert(
            session=AsyncMock(),
            user_id=uuid4(),
            alert_id="alert-1",
            data=JobAlertUpdateSchema(frequency="WEEKLY"),
        )

    assert find_by_title.await_args.kwargs["exclude_alert_id"] == "alert-1"
    update_alert.assert_awaited_once()
    assert result.frequency == "WEEKLY"


@pytest.mark.asyncio
async def test_two_different_candidates_can_use_same_alert_title():
    find_by_title = AsyncMock(return_value=None)
    candidate_ids = ["candidate-1", "candidate-2"]

    for candidate_id in candidate_ids:
        patches = _service_patches(
            candidate_id=candidate_id,
            created_alert=_alert(candidate_id=candidate_id),
        )
        with patches[0], patches[1], patches[2], patches[3], patch(
            "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
            find_by_title,
        ), patches[5], patches[6], patches[7], patches[8]:
            await CandidateProfileService.create_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                data=JobAlertUpsertSchema(**_valid_payload(title="Alert1")),
            )

    assert [
        call.kwargs["candidate_id"]
        for call in find_by_title.await_args_list
    ] == candidate_ids


@pytest.mark.asyncio
async def test_existing_criteria_duplicate_check_still_rejects_independently():
    patches = _service_patches(
        title_duplicate=None,
        criteria_duplicate=_alert(alert_id="criteria-duplicate"),
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as create_alert, patches[7], patches[8]:
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.create_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                data=JobAlertUpsertSchema(**_valid_payload()),
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Job alert already exists."
    create_alert.assert_not_awaited()


class _ScalarResult:
    def __init__(self, first_value=None):
        self.first_value = first_value

    def scalars(self):
        return self

    def first(self):
        return self.first_value


class _DuplicateRowsResult:
    def scalars(self):
        return self

    def first(self):
        return "matching-alert"

    def scalar_one_or_none(self):
        raise AssertionError("title lookup must not require exactly one matching row")


class _CaptureSession:
    def __init__(self, result=None):
        self.statement = None
        self.result = result or _ScalarResult()

    async def execute(self, statement):
        self.statement = statement
        return self.result


@pytest.mark.asyncio
async def test_title_lookup_is_per_candidate_case_insensitive_and_trims():
    session = _CaptureSession()

    await CandidateProfileRepo.find_job_alert_by_title(
        session=session,
        candidate_id="candidate-1",
        title="  alert1  ",
        exclude_alert_id="alert-1",
    )

    sql = str(session.statement).lower()

    assert "job_alerts.candidate_id" in sql
    assert "lower(trim(job_alerts.job_alert_title))" in sql
    assert "job_alerts.alert_id !=" in sql
    assert "limit" in sql


@pytest.mark.asyncio
async def test_title_lookup_tolerates_existing_duplicate_rows():
    session = _CaptureSession(result=_DuplicateRowsResult())

    result = await CandidateProfileRepo.find_job_alert_by_title(
        session=session,
        candidate_id="candidate-1",
        title="title 2",
    )

    assert result == "matching-alert"
