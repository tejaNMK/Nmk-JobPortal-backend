from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.main import init_app


class FakeSession:
    pass


@pytest.fixture()
def client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


@pytest.fixture()
def employer_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_employer_payload():
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "hr@example.com",
        }

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[employer_user_only] = fake_employer_payload
    return TestClient(app)


def test_employer_notifications_require_auth(client):
    response = client.get("/employer/notifications")

    assert response.status_code in (401, 403)


def test_employer_notifications_list_success(employer_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "items": [
                {
                    "notification_id": "note-1",
                    "title": "New application",
                    "message": "A candidate applied to your job.",
                    "notification_type": "APPLICATION_RECEIVED",
                    "is_read": False,
                    "created_at": "2026-08-03T08:00:00",
                }
            ],
            "pagination": {
                "page": 1,
                "page_size": 10,
                "total_items": 1,
                "total_pages": 1,
            },
            "unread_count": 1,
        }
    )

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.list_notifications",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.get(
            "/employer/notifications",
            headers={"Authorization": "Bearer jwt-token"},
            params={
                "page": 1,
                "page_size": 10,
                "is_read": False,
                "notification_type": "APPLICATION_RECEIVED",
                "filter": "Applications",
                "category": "Applications",
                "priority": "HIGH",
                "from_date": "2026-08-01",
                "to_date": "2026-08-03",
                "timezone": "UTC",
                "search": "candidate",
                "sort_order": "desc",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["items"][0]["notification_id"] == "note-1"
    assert body["data"]["unread_count"] == 1
    service.assert_awaited_once()


def test_employer_notifications_unread_count_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"unread_count": 3})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.unread_count",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.get(
            "/employer/notifications/unread-count",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["unread_count"] == 3
    service.assert_awaited_once()


def test_employer_notification_mark_single_read_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"updated_count": 1})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.mark_as_read",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.patch(
            "/employer/notifications/note-1/read",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["updated_count"] == 1
    service.assert_awaited_once()


def test_employer_notifications_mark_all_read_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"updated_count": 4})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.mark_all_as_read",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.patch(
            "/employer/notifications/read-all",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["updated_count"] == 4
    service.assert_awaited_once()


def test_employer_notifications_mark_many_read_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"updated_count": 2})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.mark_many_as_read",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.patch(
            "/employer/notifications/batch/read",
            headers={"Authorization": "Bearer jwt-token"},
            json={"notification_ids": ["note-1", "note-2"]},
        )

    assert response.status_code == 200
    assert response.json()["data"]["updated_count"] == 2
    service.assert_awaited_once()


def test_employer_notification_delete_single_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"deleted_count": 1})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.delete_notification",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.delete(
            "/employer/notifications/note-1",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 1
    service.assert_awaited_once()


def test_employer_notification_delete_many_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"deleted_count": 2})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.delete_many",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.request(
            "DELETE",
            "/employer/notifications/batch",
            headers={"Authorization": "Bearer jwt-token"},
            json={"notification_ids": ["note-1", "note-2"]},
        )

    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 2
    service.assert_awaited_once()


def test_employer_notifications_clear_read_success(employer_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"deleted_count": 2})

    with patch(
        "app.service.employer_service.notification_service."
        "EmployerNotificationService.clear_read_notifications",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = employer_client.delete(
            "/employer/notifications/clear-read",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 2
    service.assert_awaited_once()
