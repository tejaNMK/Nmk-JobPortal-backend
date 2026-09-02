from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


CANDIDATE_USER_ID = uuid4()
EMPLOYER_USER_ID = uuid4()


class DumpableResult:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeSession:
    pass


def _fake_user(role_code: str, user_id):
    return SimpleNamespace(
        user_id=user_id,
        roles=[SimpleNamespace(role_code=role_code)],
    )


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(CANDIDATE_USER_ID), "email": "candidate@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_CANDIDATE", CANDIDATE_USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def employer_auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(EMPLOYER_USER_ID), "email": "employer@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_EMPLOYER", EMPLOYER_USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def unauth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def _participant(**overrides):
    base = {
        "kind": "EMPLOYER",
        "employer_user_id": str(EMPLOYER_USER_ID),
        "name": "Alex Chen",
        "company_id": "co-1",
        "company_name": "Northwind",
        "company_logo": None,
    }
    base.update(overrides)
    return base


def test_list_conversations_requires_auth(unauth_client):
    response = unauth_client.get("/candidate/messages")
    assert response.status_code == 401


def test_employer_cannot_access_candidate_messages(employer_auth_client):
    response = employer_auth_client.get("/candidate/messages")
    assert response.status_code == 403


def test_list_conversations_success(auth_client):
    fake_result = DumpableResult(
        items=[
            {
                "thread_id": "thread-1",
                "subject": "Offer review",
                "participant": _participant(),
                "last_message_preview": "3pm PT works!",
                "last_message_at": "2026-07-29T10:00:00",
                "last_message_is_mine": False,
                "unread_count": 2,
            }
        ],
        total=1,
        page=1,
        page_size=20,
        total_unread=2,
    )
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.list_conversations",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.get("/candidate/messages", params={"search": "Offer"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["subject"] == "Offer review"
    assert body["data"]["items"][0]["unread_count"] == 2
    service.assert_awaited_once()


def test_get_conversation_success(auth_client):
    fake_result = DumpableResult(
        thread_id="thread-1",
        subject="Offer review",
        participant=_participant(),
        messages=[
            {
                "message_id": "m-1",
                "thread_id": "thread-1",
                "from_me": False,
                "is_system": False,
                "sender_name": "Alex Chen",
                "body": "Hey! Attaching the updated offer summary.",
                "sent_at": "2026-07-29T09:00:00",
                "read": True,
            }
        ],
    )
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.get_conversation",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.get("/candidate/messages/thread-1")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["thread_id"] == "thread-1"
    assert body["data"]["messages"][0]["body"].startswith("Hey!")
    service.assert_awaited_once()


def test_get_conversation_not_found(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.get_conversation",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Conversation not found"),
    ):
        response = auth_client.get("/candidate/messages/missing-thread")

    assert response.status_code == 404
    assert response.json()["message"] == "Conversation not found"


def test_send_reply_success(auth_client):
    fake_result = DumpableResult(
        message={
            "message_id": "m-2",
            "thread_id": "thread-1",
            "from_me": True,
            "is_system": False,
            "sender_name": None,
            "body": "Thanks, reviewing now.",
            "sent_at": "2026-07-29T10:05:00",
            "read": False,
        }
    )
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.send_reply",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.post(
            "/candidate/messages/thread-1/messages",
            json={"message": "Thanks, reviewing now."},
        )

    assert response.status_code == 201
    assert response.json()["data"]["message"]["from_me"] is True
    service.assert_awaited_once()


def test_send_reply_rejects_empty_body(auth_client):
    response = auth_client.post("/candidate/messages/thread-1/messages", json={"message": ""})
    assert response.status_code == 422


def test_send_reply_to_system_thread_rejected(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.send_reply",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=400, detail="This conversation cannot be replied to"),
    ):
        response = auth_client.post(
            "/candidate/messages/thread-1/messages",
            json={"message": "Hello?"},
        )

    assert response.status_code == 400


def test_compose_conversation_success(auth_client):
    fake_result = DumpableResult(
        thread_id="thread-new",
        message={
            "message_id": "m-3",
            "thread_id": "thread-new",
            "from_me": True,
            "is_system": False,
            "sender_name": None,
            "body": "Hi, following up on my application.",
            "sent_at": "2026-07-29T11:00:00",
            "read": False,
        },
    )
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.compose",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.post(
            "/candidate/messages",
            json={
                "company_id": "co-1",
                "subject": "Following up",
                "message": "Hi, following up on my application.",
            },
        )

    assert response.status_code == 201
    assert response.json()["data"]["thread_id"] == "thread-new"
    service.assert_awaited_once()


def test_compose_conversation_without_connection_forbidden(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.compose",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="You can only message companies you have applied to or been invited by",
        ),
    ):
        response = auth_client.post(
            "/candidate/messages",
            json={"company_id": "co-2", "subject": "Hi", "message": "Hi there"},
        )

    assert response.status_code == 403


def test_mark_conversation_read_success(auth_client):
    fake_result = DumpableResult(thread_id="thread-1", marked_read=3)
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.mark_thread_read",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.patch("/candidate/messages/thread-1/read")

    assert response.status_code == 200
    assert response.json()["data"]["marked_read"] == 3
    service.assert_awaited_once()


def test_mark_all_read_success(auth_client):
    fake_result = DumpableResult(marked_read=5)
    with patch(
        "app.controller.candidate_controller.candidate_messages.MessagingService.mark_all_read",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.patch("/candidate/messages/read-all")

    assert response.status_code == 200
    assert response.json()["data"]["marked_read"] == 5
    service.assert_awaited_once()