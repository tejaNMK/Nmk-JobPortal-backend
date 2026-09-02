from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.main import init_app
from app.schema.super_admin.dashboard_api import (
    RecentRegistrationItem,
    RecentRegistrationListResponse,
)
from app.service.super_admin.dashboard_api_service import SuperAdminDashboardService


class FakeSession:
    pass


async def fake_db():
    yield FakeSession()


def _app_with_super_admin():
    app = init_app()
    app.dependency_overrides[get_db] = fake_db

    async def fake_super_admin():
        return {"user_id": str(uuid4())}

    app.dependency_overrides[super_admin_only] = fake_super_admin
    return app


def test_dashboard_recent_registrations_route_forwards_page_filters(monkeypatch):
    captured = {}
    user_id = uuid4()
    payload = RecentRegistrationListResponse(
        items=[
            RecentRegistrationItem(
                user_id=user_id,
                full_name="Asha Rao",
                email="asha@example.com",
                role="ROLE_CANDIDATE",
                status="ACTIVE",
                created_at=datetime(2026, 8, 5, 9, 30),
            )
        ],
        total=1,
        total_records=1,
        page=2,
        page_size=25,
    )

    async def fake_list_recent_registrations(**kwargs):
        captured.update(kwargs)
        return payload

    monkeypatch.setattr(
        SuperAdminDashboardService,
        "list_recent_registrations",
        fake_list_recent_registrations,
    )

    response = TestClient(_app_with_super_admin()).get(
        "/super-admin/dashboard/recent-registrations",
        params={
            "page": 2,
            "page_size": 25,
            "search": "asha",
            "role": "candidate",
            "from_date": "2026-08-01",
            "to_date": "2026-08-05",
            "timezone": "UTC",
        },
    )

    assert response.status_code == 200
    assert captured["page"] == 2
    assert captured["page_size"] == 25
    assert captured["search"] == "asha"
    assert captured["role"] == "candidate"
    assert isinstance(captured["session"], FakeSession)
    assert captured["date_range"].from_date.isoformat() == "2026-08-01"
    assert response.json()["data"]["total_records"] == 1
    assert response.json()["data"]["items"][0]["full_name"] == "Asha Rao"


def test_recent_registrations_routes_are_present_in_openapi():
    paths = TestClient(_app_with_super_admin()).get("/openapi.json").json()["paths"]

    assert "/super-admin/recent-registrations" in paths
    assert "/super-admin/dashboard/recent-registrations" in paths
