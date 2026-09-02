import os
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/testdb",
)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_key")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "checkout-secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "webhook-secret")


from app.controller.payment import razorpay_webhook
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.schema.payment import RazorpayCreateOrderRequest
from app.service.payment_service import RazorpayPaymentService


bootstrap_mappers()


def _plan(**overrides):
    values = {
        "subscription_id": uuid4(),
        "subscription_name": "Candidate Pro",
        "subscription_type": "CANDIDATE",
        "duration_days": 30,
        "is_active": True,
        "is_default": False,
        "price": Decimal("499.00"),
        "currency": "INR",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _pending_subscription(**overrides):
    now = datetime.utcnow()
    values = {
        "user_subscription_id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "role": "CANDIDATE",
        "start_date": now,
        "end_date": now + timedelta(days=30),
        "status": "PENDING",
        "payment_status": "PENDING",
        "price_paid": Decimal("499.00"),
        "discount_amount": Decimal("0.00"),
        "currency": "INR",
        "transaction_reference": None,
        "payment_gateway": "RAZORPAY",
        "razorpay_order_id": "order_test_123",
        "razorpay_payment_id": None,
        "payment_verified_at": None,
        "remarks": None,
        "auto_renew": False,
        "assigned_by": None,
        "cancelled_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _session():
    return SimpleNamespace(refresh=AsyncMock(), add=lambda *_args, **_kwargs: None)


def _checkout_signature(order_id, payment_id):
    return RazorpayPaymentService._hmac_sha256(
        f"{order_id}|{payment_id}".encode("utf-8"),
        "checkout-secret",
    )


def _webhook_signature(body):
    return RazorpayPaymentService._hmac_sha256(body, "webhook-secret")


def _provider_order(subscription):
    return {
        "id": subscription.razorpay_order_id,
        "amount": int(Decimal(str(subscription.price_paid)) * 100),
        "currency": subscription.currency,
        "status": "paid",
    }


def _provider_payment(subscription, payment_id="pay_real_123", **overrides):
    values = {
        "id": payment_id,
        "order_id": subscription.razorpay_order_id,
        "amount": int(Decimal(str(subscription.price_paid)) * 100),
        "currency": subscription.currency,
        "status": "captured",
    }
    values.update(overrides)
    return values


def test_checkout_signature_uses_order_id_payment_id_and_secret():
    order_id = "order_test_123"
    payment_id = "pay_test_456"
    signature = _checkout_signature(order_id, payment_id)

    assert RazorpayPaymentService.verify_checkout_signature(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
    )
    assert not RazorpayPaymentService.verify_checkout_signature(
        order_id=order_id,
        payment_id="pay_tampered",
        signature=signature,
    )


def test_webhook_signature_uses_raw_body_and_webhook_secret():
    body = b'{"event":"payment.captured"}'
    signature = _webhook_signature(body)

    assert RazorpayPaymentService.verify_webhook_signature(
        body=body,
        signature=signature,
    )
    assert not RazorpayPaymentService.verify_webhook_signature(
        body=b'{"event":"payment.failed"}',
        signature=signature,
    )


@pytest.mark.asyncio
async def test_create_order_uses_db_price_and_stores_pending_subscription(monkeypatch):
    user_id = uuid4()
    plan = _plan(subscription_id=uuid4(), price=Decimal("499.00"), currency="INR")
    captured_subscription = {}

    async def fake_create(*, session, user_subscription, commit):
        captured_subscription["row"] = user_subscription
        user_subscription.user_subscription_id = uuid4()
        return user_subscription

    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_active_subscription",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService._razorpay_request",
        AsyncMock(return_value={"id": "order_real_from_razorpay"}),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.create",
        fake_create,
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.add_history",
        AsyncMock(),
    )
    monkeypatch.setattr("app.service.payment_service.commit_rollback", AsyncMock())

    response = await RazorpayPaymentService.create_subscription_order(
        session=_session(),
        user_id=user_id,
        request=RazorpayCreateOrderRequest(subscription_id=plan.subscription_id),
    )

    order_call = RazorpayPaymentService._razorpay_request.await_args.kwargs["json"]
    pending = captured_subscription["row"]

    assert order_call["amount"] == 49900
    assert order_call["currency"] == "INR"
    assert order_call["notes"]["user_id"] == str(user_id)
    assert pending.status == "PENDING"
    assert pending.payment_status == "PENDING"
    assert pending.price_paid == Decimal("499.00")
    assert pending.razorpay_order_id == "order_real_from_razorpay"
    assert response.key == "rzp_test_key"
    assert not hasattr(response, "key_secret")


@pytest.mark.asyncio
async def test_create_order_rejects_existing_pending_payment_before_razorpay(monkeypatch):
    user_id = uuid4()
    plan = _plan(subscription_id=uuid4())
    pending = _pending_subscription(
        user_id=user_id,
        subscription_id=plan.subscription_id,
    )
    razorpay_request = AsyncMock()
    reconcile = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.reconcile_pending_order",
        reconcile,
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService._razorpay_request",
        razorpay_request,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.create_subscription_order(
            session=_session(),
            user_id=user_id,
            request=RazorpayCreateOrderRequest(subscription_id=plan.subscription_id),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SUBSCRIPTION_PAYMENT_PENDING"
    assert exc.value.detail["same_plan"] is True
    assert exc.value.detail["razorpay_order_id"] == pending.razorpay_order_id
    reconcile.assert_awaited_once()
    razorpay_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_order_blocks_plan_change_when_payment_is_pending(monkeypatch):
    user_id = uuid4()
    plan = _plan(subscription_id=uuid4())
    pending = _pending_subscription(
        user_id=user_id,
        subscription_id=uuid4(),
    )
    razorpay_request = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.reconcile_pending_order",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService._razorpay_request",
        razorpay_request,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.create_subscription_order(
            session=_session(),
            user_id=user_id,
            request=RazorpayCreateOrderRequest(subscription_id=plan.subscription_id),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SUBSCRIPTION_PAYMENT_PENDING"
    assert exc.value.detail["same_plan"] is False
    assert "choosing another subscription plan" in exc.value.detail["message"]
    razorpay_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_order_rejects_free_plan_before_contacting_razorpay(monkeypatch):
    plan = _plan(price=Decimal("0.00"))

    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    razorpay_request = AsyncMock()
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService._razorpay_request",
        razorpay_request,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.create_subscription_order(
            session=_session(),
            user_id=uuid4(),
            request=RazorpayCreateOrderRequest(subscription_id=plan.subscription_id),
        )

    assert exc.value.status_code == 400
    assert "free plans" in exc.value.detail.lower()
    razorpay_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_pending_payment_returns_empty_when_none_exists(monkeypatch):
    user_id = uuid4()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=None),
    )

    response = await RazorpayPaymentService.get_pending_subscription_payment(
        session=_session(),
        user_id=user_id,
        role="CANDIDATE",
    )

    assert response.has_pending is False
    assert response.order_id is None


@pytest.mark.asyncio
async def test_get_pending_payment_returns_resumable_order(monkeypatch):
    user_id = uuid4()
    plan = _plan(subscription_id=uuid4(), price=Decimal("499.00"))
    pending = _pending_subscription(
        user_id=user_id,
        subscription_id=plan.subscription_id,
    )
    reconcile = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.reconcile_pending_order",
        reconcile,
    )

    response = await RazorpayPaymentService.get_pending_subscription_payment(
        session=_session(),
        user_id=user_id,
        role="CANDIDATE",
    )

    assert response.has_pending is True
    assert response.key == "rzp_test_key"
    assert response.order_id == pending.razorpay_order_id
    assert response.amount == 49900
    assert response.currency == "INR"
    assert response.subscription_id == plan.subscription_id
    assert response.plan_name == "Candidate Pro"
    reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_pending_payment_sync_returns_resolved_when_reconciled(monkeypatch):
    user_id = uuid4()
    pending = _pending_subscription(user_id=user_id)

    async def fake_reconcile(_session, user_subscription):
        user_subscription.status = "ACTIVE"
        user_subscription.payment_status = "PAID"
        return True

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._ensure_user_and_role",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_pending_razorpay_subscription",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.reconcile_pending_order",
        AsyncMock(side_effect=fake_reconcile),
    )

    response = await RazorpayPaymentService.get_pending_subscription_payment(
        session=_session(),
        user_id=user_id,
        role="CANDIDATE",
        sync=True,
    )

    assert response.has_pending is False
    assert response.resolved is True
    assert response.status == "ACTIVE"
    assert response.payment_status == "PAID"


@pytest.mark.asyncio
async def test_verify_checkout_rejects_invalid_signature_without_activating(monkeypatch):
    complete_payment = AsyncMock()
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.complete_order_payment",
        complete_payment,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.verify_checkout_payment(
            session=_session(),
            user_id=uuid4(),
            razorpay_order_id="order_test_123",
            razorpay_payment_id="pay_test_456",
            razorpay_signature="tampered",
        )

    assert exc.value.status_code == 400
    complete_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_checkout_rejects_order_owned_by_another_user(monkeypatch):
    owner_id = uuid4()
    attacker_id = uuid4()
    pending = _pending_subscription(user_id=owner_id)

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=pending),
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.verify_checkout_payment(
            session=_session(),
            user_id=attacker_id,
            razorpay_order_id=pending.razorpay_order_id,
            razorpay_payment_id="pay_test_456",
            razorpay_signature=_checkout_signature(
                pending.razorpay_order_id,
                "pay_test_456",
            ),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_complete_order_payment_requires_payment_id(monkeypatch):
    pending = _pending_subscription()
    plan_lookup = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        plan_lookup,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.complete_order_payment(
            session=_session(),
            razorpay_order_id=pending.razorpay_order_id,
            razorpay_payment_id="",
            source="webhook",
        )

    assert exc.value.status_code == 400
    assert "payment id is required" in exc.value.detail.lower()
    plan_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_order_payment_activates_pending_subscription_once(monkeypatch):
    pending = _pending_subscription()
    plan = _plan(subscription_id=pending.subscription_id)
    calls = []

    async def fake_update(**kwargs):
        calls.append("update")
        return kwargs["subscription"]

    async def fake_expire_duplicates(**_kwargs):
        calls.append("expire_duplicates")
        return 1

    update = AsyncMock(side_effect=fake_update)
    expire_duplicates = AsyncMock(side_effect=fake_expire_duplicates)
    add_history = AsyncMock()
    log_activity = AsyncMock()
    notify = AsyncMock()
    commit = AsyncMock()
    session = _session()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.update",
        update,
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.expire_duplicate_active_subscriptions",
        expire_duplicates,
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.add_history",
        add_history,
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order",
        AsyncMock(return_value=_provider_order(pending)),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_payment",
        AsyncMock(return_value=_provider_payment(pending)),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._log_user_subscription_activity",
        log_activity,
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionService._notify_subscription_event",
        notify,
    )
    monkeypatch.setattr("app.service.payment_service.commit_rollback", commit)

    response = await RazorpayPaymentService.complete_order_payment(
        session=session,
        razorpay_order_id=pending.razorpay_order_id,
        razorpay_payment_id="pay_real_123",
        source="checkout",
        expected_user_id=pending.user_id,
    )

    assert pending.status == "ACTIVE"
    assert pending.payment_status == "PAID"
    assert pending.transaction_reference == "pay_real_123"
    assert pending.razorpay_payment_id == "pay_real_123"
    assert pending.payment_verified_at is not None
    assert response.payment_status == "PAID"
    expire_duplicates.assert_awaited_once()
    assert calls == ["expire_duplicates", "update"]
    add_history.assert_awaited_once()
    log_activity.assert_awaited_once()
    notify.assert_awaited_once()
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_order_payment_rejects_uncaptured_provider_payment(monkeypatch):
    pending = _pending_subscription()
    plan = _plan(subscription_id=pending.subscription_id)
    update = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order",
        AsyncMock(return_value=_provider_order(pending)),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_payment",
        AsyncMock(return_value=_provider_payment(pending, status="authorized")),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.update",
        update,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.complete_order_payment(
            session=_session(),
            razorpay_order_id=pending.razorpay_order_id,
            razorpay_payment_id="pay_real_123",
        )

    assert exc.value.status_code == 409
    assert "not captured" in exc.value.detail.lower()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_order_payment_rejects_provider_amount_mismatch(monkeypatch):
    pending = _pending_subscription()
    plan = _plan(subscription_id=pending.subscription_id)
    update = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=pending),
    )
    monkeypatch.setattr(
        "app.service.payment_service.SubscriptionRepository.get_by_id",
        AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order",
        AsyncMock(return_value=_provider_order(pending)),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_payment",
        AsyncMock(return_value=_provider_payment(pending, amount=1)),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.update",
        update,
    )

    with pytest.raises(HTTPException) as exc:
        await RazorpayPaymentService.complete_order_payment(
            session=_session(),
            razorpay_order_id=pending.razorpay_order_id,
            razorpay_payment_id="pay_real_123",
        )

    assert exc.value.status_code == 400
    assert "amount mismatch" in exc.value.detail.lower()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_order_payment_is_idempotent_for_already_paid_order(monkeypatch):
    active = _pending_subscription(
        status="ACTIVE",
        payment_status="PAID",
        transaction_reference="pay_real_123",
    )
    update = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.get_by_razorpay_order_id_for_update",
        AsyncMock(return_value=active),
    )
    monkeypatch.setattr(
        "app.service.payment_service.UserSubscriptionRepository.update",
        update,
    )

    response = await RazorpayPaymentService.complete_order_payment(
        session=_session(),
        razorpay_order_id=active.razorpay_order_id,
        razorpay_payment_id="pay_real_123",
        source="webhook",
    )

    assert response.status == "ACTIVE"
    assert response.transaction_reference == "pay_real_123"
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(monkeypatch):
    class FakeRequest:
        async def body(self):
            return b'{"event":"payment.captured"}'

    complete_payment = AsyncMock()
    monkeypatch.setattr(
        "app.controller.payment.RazorpayPaymentService.complete_order_payment",
        complete_payment,
    )

    with pytest.raises(HTTPException) as exc:
        await razorpay_webhook(
            request=FakeRequest(),
            x_razorpay_signature="bad-signature",
            session=_session(),
        )

    assert exc.value.status_code == 400
    complete_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_processes_payment_captured_with_signature(monkeypatch):
    body = (
        b'{"event":"payment.captured","payload":{"payment":{"entity":'
        b'{"id":"pay_real_123","order_id":"order_test_123",'
        b'"amount":49900,"currency":"INR","status":"captured"}}}}'
    )
    verified = SimpleNamespace(
        model_dump=lambda: {
            "status": "ACTIVE",
            "payment_status": "PAID",
        }
    )
    complete_payment = AsyncMock(return_value=verified)

    class FakeRequest:
        async def body(self):
            return body

    session = _session()
    monkeypatch.setattr(
        "app.controller.payment.RazorpayPaymentService.complete_order_payment",
        complete_payment,
    )

    response = await razorpay_webhook(
        request=FakeRequest(),
        x_razorpay_signature=_webhook_signature(body),
        session=session,
    )

    assert response.data["processed"] is True
    assert response.data["order_id"] == "order_test_123"
    assert response.data["payment_id"] == "pay_real_123"
    complete_payment.assert_awaited_once_with(
        session=session,
        razorpay_order_id="order_test_123",
        razorpay_payment_id="pay_real_123",
        source="webhook",
        provider_order=None,
        provider_payment={
            "id": "pay_real_123",
            "order_id": "order_test_123",
            "amount": 49900,
            "currency": "INR",
            "status": "captured",
        },
    )


@pytest.mark.asyncio
async def test_scheduler_reconciles_paid_order_only_when_payment_id_exists(monkeypatch):
    pending = _pending_subscription()
    complete_payment = AsyncMock()
    session = _session()

    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order",
        AsyncMock(return_value={"status": "paid"}),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order_payments",
        AsyncMock(return_value=[{"id": "pay_real_123", "status": "captured"}]),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.complete_order_payment",
        complete_payment,
    )

    processed = await RazorpayPaymentService.reconcile_pending_order(
        session,
        pending,
    )

    assert processed is True
    complete_payment.assert_awaited_once_with(
        session=session,
        razorpay_order_id=pending.razorpay_order_id,
        razorpay_payment_id="pay_real_123",
        source="scheduler",
    )


@pytest.mark.asyncio
async def test_scheduler_does_not_activate_paid_order_without_payment_id(monkeypatch):
    pending = _pending_subscription()
    complete_payment = AsyncMock()

    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order",
        AsyncMock(return_value={"status": "paid"}),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.fetch_order_payments",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.service.payment_service.RazorpayPaymentService.complete_order_payment",
        complete_payment,
    )

    processed = await RazorpayPaymentService.reconcile_pending_order(
        _session(),
        pending,
    )

    assert processed is False
    complete_payment.assert_not_awaited()
