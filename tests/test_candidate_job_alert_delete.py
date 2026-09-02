from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.repository.candidate_repo import CandidateProfileRepo
from app.service.candidate_service import CandidateProfileService


VALID_ALERT_ID = "1289effa4b764b9f83029e1f79e33b9b"


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DeleteSession:
    def __init__(self, alert):
        self.alert = alert
        self.statements = []
        self.deleted = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _ScalarResult(self.alert)
        return _ScalarResult(None)

    async def delete(self, item):
        self.deleted.append(item)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


async def _call_delete_service(*, repo_deleted=True, alert_id=VALID_ALERT_ID):
    user_id = uuid4()
    delete_alert = AsyncMock(return_value=repo_deleted)

    with (
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(candidate_id="candidate-1"),
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.delete_job_alert",
            delete_alert,
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await CandidateProfileService.delete_job_alert(
            session=AsyncMock(),
            user_id=user_id,
            alert_id=alert_id,
        )

    return result, delete_alert


@pytest.mark.asyncio
async def test_candidate_can_delete_their_own_job_alert():
    result, delete_alert = await _call_delete_service()

    assert result == {"message": "Job alert deleted successfully"}
    delete_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleted_alert_is_removed_by_repository_after_disassociating_deliveries():
    alert = SimpleNamespace(alert_id=VALID_ALERT_ID, candidate_id="candidate-1")
    session = _DeleteSession(alert)

    deleted = await CandidateProfileRepo.delete_job_alert(
        session=session,
        candidate_id="candidate-1",
        alert_id=VALID_ALERT_ID,
    )

    assert deleted is True
    assert len(session.statements) == 2
    assert "job_alert_notification_deliveries" in str(session.statements[1])
    assert "alert_id=:alert_id" in str(session.statements[1])
    assert session.deleted == [alert]
    assert session.committed is True
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_deleting_nonexistent_job_alert_returns_404():
    with pytest.raises(HTTPException) as exc:
        await _call_delete_service(repo_deleted=False)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job alert not found"


@pytest.mark.asyncio
async def test_candidate_cannot_delete_another_candidates_job_alert():
    with pytest.raises(HTTPException) as exc:
        await _call_delete_service(repo_deleted=False)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_related_notification_delivery_records_do_not_block_delete():
    alert = SimpleNamespace(alert_id=VALID_ALERT_ID, candidate_id="candidate-1")
    session = _DeleteSession(alert)

    deleted = await CandidateProfileRepo.delete_job_alert(
        session=session,
        candidate_id="candidate-1",
        alert_id=VALID_ALERT_ID,
    )

    assert deleted is True
    assert session.deleted == [alert]
    assert session.committed is True


@pytest.mark.asyncio
async def test_malformed_job_alert_id_returns_400_without_repository_call():
    with patch(
        "app.service.candidate_service.CandidateProfileRepo.delete_job_alert",
        new_callable=AsyncMock,
    ) as delete_alert:
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.delete_job_alert(
                session=AsyncMock(),
                user_id=uuid4(),
                alert_id="not-a-valid-alert-id",
            )

    assert exc.value.status_code == 400
    assert delete_alert.await_count == 0


@pytest.mark.asyncio
async def test_repeated_delete_returns_404_after_first_delete():
    _, delete_alert = await _call_delete_service(repo_deleted=True)
    assert delete_alert.await_count == 1

    with pytest.raises(HTTPException) as exc:
        await _call_delete_service(repo_deleted=False)

    assert exc.value.status_code == 404
