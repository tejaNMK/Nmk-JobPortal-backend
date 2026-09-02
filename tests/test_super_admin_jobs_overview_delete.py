from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.main import init_app
from app.schema.super_admin.dashboard_api import SuperAdminJobBulkActionRequest
from app.service.super_admin.dashboard_api_service import SuperAdminDashboardService


class FakeSession:
    pass


async def fake_db():
    yield FakeSession()


def _app_with_super_admin():
    app = init_app()

    async def fake_super_admin():
        return {"user_id": str(uuid4()), "roles": ["ROLE_SUPER_ADMIN"]}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[super_admin_only] = fake_super_admin
    return app


def test_super_admin_bulk_job_delete_accepts_uppercase_action():
    request = SuperAdminJobBulkActionRequest(
        job_ids=["job-1"],
        action="DELETE",
    )

    assert request.action == "delete"


def test_super_admin_delete_job_endpoint_deletes_single_job(monkeypatch):
    app = _app_with_super_admin()
    captured = {}

    async def fake_bulk_action_jobs(session, job_ids, action, actor, reason=None):
        captured["job_ids"] = job_ids
        captured["action"] = action
        captured["actor"] = actor
        captured["reason"] = reason
        return SimpleNamespace(
            updated=1,
            model_dump=lambda: {
                "action": "DELETE",
                "requested": 1,
                "updated": 1,
                "job_ids": job_ids,
            },
        )

    monkeypatch.setattr(
        SuperAdminDashboardService,
        "bulk_action_jobs",
        fake_bulk_action_jobs,
    )

    response = TestClient(app).delete("/super-admin/jobs/job-1")

    assert response.status_code == 200
    assert captured["job_ids"] == ["job-1"]
    assert captured["action"] == "delete"
    assert response.json()["message"] == "Job deleted successfully."
    assert response.json()["data"]["updated"] == 1


def test_super_admin_delete_job_endpoint_returns_404_when_not_updated(monkeypatch):
    app = _app_with_super_admin()

    async def fake_bulk_action_jobs(session, job_ids, action, actor, reason=None):
        return SimpleNamespace(
            updated=0,
            model_dump=lambda: {
                "action": "DELETE",
                "requested": 1,
                "updated": 0,
                "job_ids": job_ids,
            },
        )

    monkeypatch.setattr(
        SuperAdminDashboardService,
        "bulk_action_jobs",
        fake_bulk_action_jobs,
    )

    response = TestClient(app).delete("/super-admin/jobs/missing-job")

    assert response.status_code == 404
    assert response.json()["message"] == "Job not found."


@pytest.mark.asyncio
async def test_super_admin_bulk_delete_soft_deletes_posted_job(monkeypatch):
    captured = {}

    async def fake_bulk_update_jobs(session, job_ids, action, actor_id=None, reason=None):
        captured["job_ids"] = job_ids
        captured["action"] = action
        captured["actor_id"] = actor_id
        return 1

    async def fake_log(**kwargs):
        captured["log"] = kwargs

    monkeypatch.setattr(
        "app.service.super_admin.dashboard_api_service."
        "SuperAdminDashboardRepository.bulk_update_jobs",
        fake_bulk_update_jobs,
    )
    monkeypatch.setattr(
        "app.service.super_admin.dashboard_api_service.ActivityLogService.create_log",
        fake_log,
    )

    result = await SuperAdminDashboardService.bulk_action_jobs(
        session=FakeSession(),
        job_ids=["posted-job-1"],
        action="delete",
        actor={"user_id": "11111111-1111-1111-1111-111111111111"},
    )

    assert captured["job_ids"] == ["posted-job-1"]
    assert captured["action"] == "delete"
    assert captured["actor_id"] == "11111111-1111-1111-1111-111111111111"
    assert captured["log"]["action"] == "DELETE"
    assert result.action == "DELETE"
    assert result.updated == 1

