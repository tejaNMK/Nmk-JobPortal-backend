from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.schema.subscription.user_subscription import (
    CurrentSubscriptionResponse,
    UserSubscriptionResponse,
    UserSubscriptionDetailsPlan,
    UserSubscriptionDetailsResponse,
    UserSubscriptionDetailsUser,
    UserSubscriptionHistoryResponse,
)
from app.service.subscription.subscription_service import SubscriptionService
from app.service.subscription.user_subscription_service import UserSubscriptionService


bootstrap_mappers()


class FakeSession:
    pass


async def fake_db():
    yield FakeSession()


def _user_subscription(**overrides):
    now = utc_now_naive()
    data = {
        "user_subscription_id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "role": "CANDIDATE",
        "start_date": now,
        "end_date": now + timedelta(days=30),
        "status": "ACTIVE",
        "payment_status": "PAID",
        "price_paid": Decimal("29.00"),
        "discount_amount": Decimal("0.00"),
        "currency": "USD",
        "transaction_reference": None,
        "invoice_number": None,
        "auto_renew": False,
        "cancelled_at": None,
        "assigned_by": None,
        "remarks": None,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _plan(**overrides):
    data = {
        "subscription_id": uuid4(),
        "subscription_name": "Growth",
        "subscription_type": "CANDIDATE",
        "description": "Growth plan",
        "price": Decimal("29.00"),
        "currency": "USD",
        "billing_cycle": "Monthly",
        "feature_flags": {},
        "max_published_jobs": None,
        "max_job_alerts": None,
        "max_resume_uploads": None,
        "max_candidate_searches": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _current_subscription_response(**overrides):
    now = utc_now_naive()
    subscription_id = uuid4()
    data = {
        "user_subscription_id": uuid4(),
        "subscription_id": subscription_id,
        "role": "CANDIDATE",
        "start_date": now,
        "end_date": now + timedelta(days=30),
        "status": "ACTIVE",
        "currency": "USD",
        "days_remaining": 30,
        "features": {},
        "subscription": {
            "subscription_id": subscription_id,
            "subscription_name": "Growth",
            "subscription_type": "CANDIDATE",
            "description": "Growth plan",
            "price": Decimal("29.00"),
            "currency": "USD",
            "duration_days": 30,
            "billing_cycle": "Monthly",
            "features": {},
            "is_featured": False,
            "is_popular": False,
            "is_default": False,
        },
    }
    data.update(overrides)
    return CurrentSubscriptionResponse(**data)


def _user_subscription_response(**overrides):
    now = utc_now_naive()
    data = {
        "user_subscription_id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "role": "CANDIDATE",
        "start_date": now,
        "end_date": now + timedelta(days=30),
        "status": "ACTIVE",
        "payment_status": "PAID",
        "price_paid": Decimal("29.00"),
        "discount_amount": Decimal("0.00"),
        "currency": "USD",
        "auto_renew": False,
        "transaction_reference": None,
        "invoice_number": None,
        "remarks": None,
        "assigned_by": None,
        "cancelled_at": None,
        "days_remaining": 30,
        "features": {},
    }
    data.update(overrides)
    return UserSubscriptionResponse(**data)


class DumpablePlan:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


def _catalogue_plan(**overrides):
    now = utc_now_naive()
    data = {
        "subscription_id": uuid4(),
        "subscription_name": "Employer Growth",
        "subscription_type": "EMPLOYER",
        "description": "Growth plan",
        "price": Decimal("999.00"),
        "currency": "INR",
        "duration_days": 30,
        "billing_cycle": "Monthly",
        "display_order": 1,
        "max_published_jobs": 20,
        "max_job_alerts": None,
        "max_resume_uploads": None,
        "max_candidate_searches": 100,
        "feature_flags": {
            "candidate_search": True,
        },
        "features": None,
        "is_featured": False,
        "is_popular": True,
        "is_active": True,
        "is_default": False,
        "created_at": now,
        "updated_at": now,
        "created_by": None,
        "updated_by": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_subscription_history_existing_user_with_multiple_subscriptions(monkeypatch):
    user_id = uuid4()
    newest = _user_subscription(user_id=user_id, status="CANCELLED")
    older = _user_subscription(
        user_id=user_id,
        status="EXPIRED",
        created_at=newest.created_at - timedelta(days=1),
    )

    async def fake_user_identity(session, user_id):
        return SimpleNamespace(user_id=user_id, email="subscriber@example.com")

    async def fake_history(session, user_id):
        return [(newest, _plan(subscription_id=newest.subscription_id)), (older, None)]

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_user_identity",
        fake_user_identity,
    )
    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_history",
        fake_history,
    )

    result = await UserSubscriptionService.get_history(FakeSession(), user_id)

    assert result.user_id == user_id
    assert result.user_email == "subscriber@example.com"
    assert result.total == 2
    assert [item.user_subscription_id for item in result.subscriptions] == [
        newest.user_subscription_id,
        older.user_subscription_id,
    ]
    assert result.subscriptions[0].user_email == "subscriber@example.com"
    assert result.subscriptions[0].subscription_name == "Growth"
    assert result.subscriptions[1].subscription_name is None


@pytest.mark.asyncio
async def test_subscription_history_existing_user_with_no_subscriptions(monkeypatch):
    async def fake_user_identity(session, user_id):
        return SimpleNamespace(user_id=user_id, email="empty@example.com")

    async def fake_history(session, user_id):
        return []

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_user_identity",
        fake_user_identity,
    )
    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_history",
        fake_history,
    )

    result = await UserSubscriptionService.get_history(FakeSession(), uuid4())

    assert result.user_email == "empty@example.com"
    assert result.subscriptions == []
    assert result.total == 0


@pytest.mark.asyncio
async def test_subscription_history_missing_user_returns_404(monkeypatch):
    async def fake_user_identity(session, user_id):
        return None

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_user_identity",
        fake_user_identity,
    )

    with pytest.raises(HTTPException) as exc:
        await UserSubscriptionService.get_history(FakeSession(), uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found."


@pytest.mark.asyncio
async def test_list_subscribers_includes_user_email_and_name(monkeypatch):
    user_id = uuid4()
    subscription = _user_subscription(user_id=user_id)
    plan = _plan(subscription_id=subscription.subscription_id)
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Asha",
        middle_name=None,
        last_name="Rao",
        email="asha.rao@example.com",
    )

    async def fake_list_by_active_state(session, *, active, role=None):
        return [(subscription, plan, user)]

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_by_active_state",
        fake_list_by_active_state,
    )

    result = await UserSubscriptionService.list_subscribers(
        FakeSession(),
        active=True,
        role="CANDIDATE",
    )

    assert len(result) == 1
    assert result[0].user_id == user_id
    assert result[0].user_email == "asha.rao@example.com"
    assert result[0].user_name == "Asha Rao"


@pytest.mark.asyncio
async def test_subscription_details_existing_record_includes_user_and_plan(monkeypatch):
    user_subscription = _user_subscription(status="ACTIVE", auto_renew=True)
    user = SimpleNamespace(
        user_id=user_subscription.user_id,
        first_name="Nina",
        middle_name=None,
        last_name="Khan",
        email="nina@example.com",
    )
    plan = _plan(subscription_id=user_subscription.subscription_id)

    async def fake_details(session, user_subscription_id):
        return user_subscription, user, plan

    async def fake_expire(**kwargs):
        return kwargs["user_subscription"]

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_by_id_with_details",
        fake_details,
    )
    monkeypatch.setattr(UserSubscriptionService, "_expire_if_needed", fake_expire)

    result = await UserSubscriptionService.get_details(
        FakeSession(),
        user_subscription.user_subscription_id,
    )

    assert result.user_subscription_id == user_subscription.user_subscription_id
    assert result.user.name == "Nina Khan"
    assert result.user.email == "nina@example.com"
    assert result.user.role == "CANDIDATE"
    assert result.subscription.name == "Growth"
    assert result.auto_renew is True


@pytest.mark.asyncio
async def test_subscription_details_missing_record_returns_404(monkeypatch):
    async def fake_details(session, user_subscription_id):
        return None

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_by_id_with_details",
        fake_details,
    )

    with pytest.raises(HTTPException) as exc:
        await UserSubscriptionService.get_details(FakeSession(), uuid4())

    assert exc.value.status_code == 404
    assert exc.value.detail == "Subscription not found."


@pytest.mark.asyncio
async def test_subscription_details_missing_optional_relationships_do_not_error(monkeypatch):
    user_subscription = _user_subscription()

    async def fake_details(session, user_subscription_id):
        return user_subscription, None, None

    async def fake_expire(**kwargs):
        return kwargs["user_subscription"]

    monkeypatch.setattr(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_by_id_with_details",
        fake_details,
    )
    monkeypatch.setattr(UserSubscriptionService, "_expire_if_needed", fake_expire)

    result = await UserSubscriptionService.get_details(
        FakeSession(),
        user_subscription.user_subscription_id,
    )

    assert result.user.name == ""
    assert result.user.email == ""
    assert result.subscription.name == ""
    assert result.subscription.price == Decimal("0")


def _app_with_super_admin(monkeypatch, *, non_super_admin=False):
    app = init_app()
    app.dependency_overrides[get_db] = fake_db

    if non_super_admin:
        async def fake_payload():
            return {"user_id": str(uuid4())}

        async def fake_find_user(session, user_id):
            return SimpleNamespace(
                roles=[SimpleNamespace(role_code="ROLE_CANDIDATE")]
            )

        app.dependency_overrides[get_jwt_payload_401] = fake_payload
        monkeypatch.setattr(
            "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
            fake_find_user,
        )
    else:
        from app.dependencies.role_dependencies import super_admin_only

        async def fake_super_admin():
            return {"user_id": str(uuid4())}

        app.dependency_overrides[super_admin_only] = fake_super_admin

    return app


def test_history_endpoint_success_and_invalid_uuid(monkeypatch):
    user_id = uuid4()
    payload = UserSubscriptionHistoryResponse(
        user_id=user_id,
        subscriptions=[],
        total=0,
    )

    async def fake_history(session, user_id):
        return payload

    app = _app_with_super_admin(monkeypatch)
    monkeypatch.setattr(UserSubscriptionService, "get_history", fake_history)
    client = TestClient(app)

    response = client.get(f"/super-admin/user-subscriptions/{user_id}/history")

    assert response.status_code == 200
    assert response.json()["message"] == "Subscription history fetched successfully"
    assert response.json()["data"]["total"] == 0
    assert client.get("/super-admin/user-subscriptions/not-a-uuid/history").status_code == 422


def test_details_endpoint_reaches_details_controller_and_invalid_uuid(monkeypatch):
    user_subscription_id = uuid4()
    called = {"details": False}
    payload = UserSubscriptionDetailsResponse(
        user_subscription_id=user_subscription_id,
        user=UserSubscriptionDetailsUser(user_id=uuid4(), role="CANDIDATE"),
        subscription=UserSubscriptionDetailsPlan(
            subscription_id=uuid4(),
            price=Decimal("0"),
        ),
        status="ACTIVE",
        start_date=utc_now_naive(),
        end_date=utc_now_naive() + timedelta(days=30),
        auto_renew=False,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )

    async def fake_details(session, user_subscription_id):
        called["details"] = True
        return payload

    async def fail_history(session, user_id):
        raise AssertionError("details route was handled as history")

    app = _app_with_super_admin(monkeypatch)
    monkeypatch.setattr(UserSubscriptionService, "get_details", fake_details)
    monkeypatch.setattr(UserSubscriptionService, "get_history", fail_history)
    client = TestClient(app)

    response = client.get(
        f"/super-admin/user-subscriptions/details/{user_subscription_id}"
    )

    assert response.status_code == 200
    assert called["details"] is True
    assert response.json()["message"] == "Subscription details fetched successfully"
    assert client.get("/super-admin/user-subscriptions/details/not-a-uuid").status_code == 422


def test_user_subscription_routes_reject_non_super_admin(monkeypatch):
    app = _app_with_super_admin(monkeypatch, non_super_admin=True)
    client = TestClient(app)

    response = client.get(
        f"/super-admin/user-subscriptions/details/{uuid4()}",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "Only Super Admin can access this resource"


def test_super_admin_lifecycle_routes_update_subscription_status(monkeypatch):
    user_id = uuid4()
    user_subscription_id = uuid4()
    current = _user_subscription_response(
        user_id=user_id,
        user_subscription_id=user_subscription_id,
    )
    captured = []

    async def fake_get_by_id(session, user_subscription_id):
        return current

    async def fake_update_status(
        session,
        user_id,
        request,
        *,
        status,
        action,
        user_subscription_id=None,
        performed_by=None,
    ):
        captured.append(
            {
                "user_id": user_id,
                "status": status,
                "action": action,
                "user_subscription_id": user_subscription_id,
                "performed_by": performed_by,
            }
        )
        return _user_subscription_response(
            user_id=user_id,
            user_subscription_id=user_subscription_id,
            status=status,
        )

    app = _app_with_super_admin(monkeypatch)
    monkeypatch.setattr(UserSubscriptionService, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(UserSubscriptionService, "update_status", fake_update_status)
    client = TestClient(app)

    for path, expected_status, expected_action in (
        ("suspend", "SUSPENDED", "SUSPENDED"),
        ("resume", "ACTIVE", "RESUMED"),
        ("expire", "EXPIRED", "EXPIRED"),
    ):
        response = client.patch(
            f"/super-admin/user-subscriptions/{user_subscription_id}/{path}",
            json={"remarks": "admin action"},
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == expected_status
        assert captured[-1]["action"] == expected_action
        assert captured[-1]["user_id"] == user_id
        assert captured[-1]["user_subscription_id"] == user_subscription_id


def test_user_subscription_routes_are_present_in_openapi(monkeypatch):
    app = _app_with_super_admin(monkeypatch)
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/super-admin/user-subscriptions/{user_id}/history" in paths
    assert "/super-admin/user-subscriptions/users/{user_id}/history" in paths
    assert "/super-admin/user-subscriptions/details/{user_subscription_id}" in paths
    assert "/subscriptions/plans" in paths
    assert "/user/subscription/plans" in paths
    assert "/user/subscription/history" in paths
    assert "/users/{user_id}/subscription/plans" not in paths
    assert "/users/{user_id}/subscription" not in paths
    assert "/users/{user_id}/subscription/renew" not in paths
    assert "/users/{user_id}/subscription/upgrade" not in paths
    assert "/users/{user_id}/subscription/downgrade" not in paths
    assert "/users/{user_id}/subscription/cancel" not in paths
    assert "/users/{user_id}/subscription/suspend" not in paths
    assert "/users/{user_id}/subscription/resume" not in paths
    assert "/users/{user_id}/subscription/expire" not in paths
    assert "/users/{user_id}/subscription/history" not in paths
    assert "/users/{user_id}/subscription/usage" not in paths
    assert "/users/{user_id}/subscription/remaining-usage" not in paths
    assert "/users/{user_id}/subscription/usage/reset" not in paths


def test_plan_catalogue_route_uses_response_schema(monkeypatch):
    plan_id = uuid4()

    async def fake_payload():
        return {"user_id": str(uuid4())}

    async def fake_catalogue(session, payload, **filters):
        assert filters["subscription_type"] == "EMPLOYER"
        assert filters["status"] == "active"
        return [
            DumpablePlan(
                subscription_id=str(plan_id),
                subscription_name="Employer Pro",
                subscription_type="EMPLOYER",
                description="Plan description",
                price="999.00",
                currency="INR",
                duration_days=30,
                billing_cycle="Monthly",
                display_order=1,
                max_published_jobs=20,
                max_candidate_searches=100,
                feature_flags={"candidate_search": True},
                features={"candidate_search": True},
                is_featured=False,
                is_popular=True,
                is_active=True,
                is_default=False,
                is_current=True,
            )
        ]

    app = init_app()
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    monkeypatch.setattr(
        SubscriptionService,
        "get_catalogue_for_payload",
        fake_catalogue,
    )

    response = TestClient(app).get(
        "/subscriptions/plans?subscription_type=EMPLOYER&status=active",
        headers={"Authorization": "Bearer token"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["message"] == "Subscription plans fetched successfully."
    assert body["error"] is None
    assert body["data"][0]["is_current"] is True


def test_plan_catalogue_requires_authentication():
    response = TestClient(init_app()).get(
        "/subscriptions/plans?subscription_type=EMPLOYER&status=active"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_employer_catalogue_lists_all_active_employer_plans(monkeypatch):
    user_id = uuid4()
    current_plan = _catalogue_plan(subscription_name="Employer Basic")
    other_plan = _catalogue_plan(subscription_name="Employer Pro")
    inactive_plan = _catalogue_plan(subscription_name="Dormant", is_active=False)
    captured = {}

    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_EMPLOYER")])

    async def fake_get_active_subscription(session, user_id, role=None, **kwargs):
        return _user_subscription(
            user_id=user_id,
            subscription_id=current_plan.subscription_id,
            role=role,
        )

    async def fake_get_all(session, **kwargs):
        captured.update(kwargs)
        return [current_plan, other_plan]

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UserSubscriptionRepository.get_active_subscription",
        fake_get_active_subscription,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fake_get_all,
    )

    result = await SubscriptionService.get_catalogue_for_payload(
        FakeSession(),
        payload={"user_id": str(user_id)},
        subscription_type="EMPLOYER",
        status="active",
    )

    assert captured["subscription_type"] == "EMPLOYER"
    assert captured["status"] == "active"
    assert [item.subscription_name for item in result] == ["Employer Basic", "Employer Pro"]
    assert inactive_plan.subscription_id not in {item.subscription_id for item in result}
    assert result[0].is_current is True
    assert result[1].is_current is False


@pytest.mark.asyncio
async def test_employer_catalogue_keeps_other_plans_visible_after_subscription_change(monkeypatch):
    user_id = uuid4()
    old_plan = _catalogue_plan(subscription_name="Employer Basic")
    new_current_plan = _catalogue_plan(subscription_name="Employer Pro")
    next_plan = _catalogue_plan(subscription_name="Employer Scale")

    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_EMPLOYER")])

    async def fake_get_active_subscription(session, user_id, role=None, **kwargs):
        return _user_subscription(
            user_id=user_id,
            subscription_id=new_current_plan.subscription_id,
            role=role,
        )

    async def fake_get_all(session, **kwargs):
        return [old_plan, new_current_plan, next_plan]

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UserSubscriptionRepository.get_active_subscription",
        fake_get_active_subscription,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fake_get_all,
    )

    result = await SubscriptionService.get_catalogue_for_payload(
        FakeSession(),
        payload={"user_id": str(user_id)},
        subscription_type="EMPLOYER",
        status="active",
    )

    assert [item.subscription_name for item in result] == [
        "Employer Basic",
        "Employer Pro",
        "Employer Scale",
    ]
    assert [item.is_current for item in result] == [False, True, False]


@pytest.mark.asyncio
async def test_candidate_catalogue_lists_active_candidate_plans(monkeypatch):
    candidate_plan = _catalogue_plan(
        subscription_name="Candidate Growth",
        subscription_type="CANDIDATE",
        max_published_jobs=None,
        max_resume_uploads=5,
        max_candidate_searches=None,
        feature_flags={"resume_upload": True},
    )
    captured = {}

    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_CANDIDATE")])

    async def fake_get_active_subscription(session, user_id, role=None, **kwargs):
        return None

    async def fake_get_all(session, **kwargs):
        captured.update(kwargs)
        return [candidate_plan]

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UserSubscriptionRepository.get_active_subscription",
        fake_get_active_subscription,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fake_get_all,
    )

    result = await SubscriptionService.get_catalogue_for_payload(
        FakeSession(),
        payload={"user_id": str(uuid4())},
        subscription_type="CANDIDATE",
        status="active",
    )

    assert captured["subscription_type"] == "CANDIDATE"
    assert captured["status"] == "active"
    assert result[0].subscription_type == "CANDIDATE"
    assert result[0].is_current is False


@pytest.mark.asyncio
async def test_employer_catalogue_rejects_candidate_and_admin_plans(monkeypatch):
    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_EMPLOYER")])

    async def fail_get_all(session, **kwargs):
        raise AssertionError("incompatible catalogue requests should not query plans")

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fail_get_all,
    )

    for subscription_type in ("CANDIDATE", "ADMIN"):
        with pytest.raises(HTTPException) as exc:
            await SubscriptionService.get_catalogue_for_payload(
                FakeSession(),
                payload={"user_id": str(uuid4())},
                subscription_type=subscription_type,
                status="active",
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_candidate_catalogue_rejects_employer_and_admin_plans(monkeypatch):
    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_CANDIDATE")])

    async def fail_get_all(session, **kwargs):
        raise AssertionError("incompatible catalogue requests should not query plans")

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fail_get_all,
    )

    for subscription_type in ("EMPLOYER", "ADMIN"):
        with pytest.raises(HTTPException) as exc:
            await SubscriptionService.get_catalogue_for_payload(
                FakeSession(),
                payload={"user_id": str(uuid4())},
                subscription_type=subscription_type,
                status="active",
            )
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_catalogue_can_read_all_types_and_statuses(monkeypatch):
    admin_plan = _catalogue_plan(subscription_type="ADMIN", is_active=False)
    captured = {}

    async def fake_find_user(session, user_id):
        return SimpleNamespace(roles=[SimpleNamespace(role_code="ROLE_SUPER_ADMIN")])

    async def fake_get_all(session, **kwargs):
        captured.update(kwargs)
        return [admin_plan]

    monkeypatch.setattr(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        fake_get_all,
    )

    result = await SubscriptionService.get_catalogue_for_payload(
        FakeSession(),
        payload={"user_id": str(uuid4())},
        subscription_type="ADMIN",
        status="inactive",
    )

    assert captured["subscription_type"] == "ADMIN"
    assert captured["status"] == "inactive"
    assert result[0].subscription_type == "ADMIN"
    assert result[0].is_active is False


def test_plan_management_routes_remain_super_admin_only(monkeypatch):
    app = _app_with_super_admin(monkeypatch, non_super_admin=True)
    response = TestClient(app).get(
        "/super-admin/subscriptions",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 403


def test_my_subscription_returns_public_summary(monkeypatch):
    user_id = uuid4()
    payload = _current_subscription_response()
    captured = {}

    async def fake_payload():
        return {"user_id": str(user_id)}

    async def fake_current(session, user_id):
        captured["user_id"] = user_id
        return payload

    app = init_app()
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    monkeypatch.setattr(
        UserSubscriptionService,
        "get_current_subscription",
        fake_current,
    )

    response = TestClient(app).get(
        "/user/subscription",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == user_id
    data = response.json()["data"]
    assert data["subscription"]["subscription_name"] == "Growth"
    assert data["status"] == "ACTIVE"
    assert "payment_status" not in data
    assert "transaction_reference" not in data
    assert "assigned_by" not in data
    assert "remarks" not in data


def test_my_subscription_plans_uses_current_user_token(monkeypatch):
    user_id = uuid4()
    captured = {}

    async def fake_payload():
        return {"user_id": str(user_id)}

    async def fake_available(session, user_id):
        captured["user_id"] = user_id
        return [
            DumpablePlan(
                subscription_id=str(uuid4()),
                subscription_name="Candidate Growth",
                subscription_type="CANDIDATE",
                status="Active",
            )
        ]

    app = init_app()
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    monkeypatch.setattr(
        SubscriptionService,
        "get_available_for_user",
        fake_available,
    )

    response = TestClient(app).get(
        "/user/subscription/plans",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == user_id
    assert response.json()["data"][0]["subscription_type"] == "CANDIDATE"


def test_my_subscription_history_uses_current_user_token(monkeypatch):
    user_id = uuid4()
    captured = {}
    payload = UserSubscriptionHistoryResponse(
        user_id=user_id,
        subscriptions=[],
        total=0,
    )

    async def fake_payload():
        return {"user_id": str(user_id)}

    async def fake_history(session, user_id):
        captured["user_id"] = user_id
        return payload

    app = init_app()
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    monkeypatch.setattr(
        UserSubscriptionService,
        "get_history",
        fake_history,
    )

    response = TestClient(app).get(
        "/user/subscription/history",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert captured["user_id"] == user_id
    assert response.json()["data"]["total"] == 0
