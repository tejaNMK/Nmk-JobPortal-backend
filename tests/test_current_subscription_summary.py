import asyncio
import logging
import sys
import types
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

aiosmtplib_stub = types.ModuleType("aiosmtplib")
aiosmtplib_stub.SMTP = object
sys.modules.setdefault("aiosmtplib", aiosmtplib_stub)

from app.repository.subscription.user_subscription_repo import (
    UserSubscriptionRepository,
)
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.service.authentication.auth_service import AuthService
from app.service.authentication.users import UserService
from app.service.subscription.user_subscription_service import (
    UserSubscriptionService,
)
from app.utils.utc import utc_now_naive


bootstrap_mappers()


def _plan(**overrides):
    values = {
        "subscription_id": uuid4(),
        "subscription_name": "Premium Employer",
        "subscription_type": "EMPLOYER",
        "description": "Employer plan",
        "price": Decimal("99.00"),
        "currency": "INR",
        "duration_days": 30,
        "billing_cycle": "MONTHLY",
        "max_published_jobs": 10,
        "max_job_alerts": None,
        "max_resume_uploads": None,
        "feature_flags": {"candidate_search": True},
        "is_featured": False,
        "is_popular": True,
        "is_default": False,
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _assignment(**overrides):
    now = utc_now_naive()
    values = {
        "user_subscription_id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "role": "EMPLOYER",
        "status": "ACTIVE",
        "start_date": now - timedelta(days=1),
        "end_date": now + timedelta(days=29),
        "currency": "INR",
        "auto_renew": True,
        "created_at": now - timedelta(days=1),
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_current_subscription_query_filters_valid_active_employer_plan():
    user_id = uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    )

    asyncio.run(
        UserSubscriptionRepository.list_current_subscription_candidates(
            session=session,
            user_id=user_id,
            expected_type="EMPLOYER",
        )
    )

    sql = str(
        session.execute.await_args.args[0].compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "user_subscriptions.status = 'ACTIVE'" in sql
    assert "user_subscriptions.start_date IS NULL" in sql
    assert "user_subscriptions.end_date IS NULL" in sql
    assert "subscriptions.is_active IS true" in sql
    assert "upper(subscriptions.subscription_type) = 'EMPLOYER'" in sql
    assert "upper(user_subscriptions.role) = 'EMPLOYER'" in sql
    assert "ORDER BY user_subscriptions.start_date DESC NULLS LAST" in sql
    assert "user_subscriptions.updated_at DESC" in sql
    assert "LIMIT 2" in sql


def test_current_subscription_summary_uses_real_plan_name():
    user_id = uuid4()
    assignment = _assignment(user_id=user_id)
    plan = _plan(
        subscription_id=assignment.subscription_id,
        subscription_name="Basic Employer",
        billing_cycle="YEARLY",
    )

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        return_value=[(assignment, plan)],
    ):
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=user_id,
                expected_type="EMPLOYER",
            )
        )

    assert summary.subscription_name == "Basic Employer"
    assert summary.subscription_type == "EMPLOYER"
    assert summary.status == "ACTIVE"
    assert summary.billing_cycle == "YEARLY"
    assert summary.is_active is True


def test_current_subscription_summary_returns_default_assignment_when_missing():
    user_id = uuid4()
    default_assignment = _assignment(user_id=user_id)
    default_plan = _plan(
        subscription_id=default_assignment.subscription_id,
        subscription_name="Free Employer",
        is_default=True,
    )

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        side_effect=[[], [(default_assignment, default_plan)]],
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionBootstrapService.ensure_user_subscription",
        new_callable=AsyncMock,
        return_value=default_assignment,
    ):
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=user_id,
                expected_type="EMPLOYER",
            )
        )

    assert summary.subscription_name == "Free Employer"
    assert summary.subscription_id == default_plan.subscription_id


def test_current_subscription_summary_returns_none_without_role_or_active_plan():
    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        return_value=[],
    ):
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=uuid4(),
                expected_type=None,
            )
        )

    assert summary is None


def test_duplicate_active_subscriptions_warn_and_select_one(caplog):
    user_id = uuid4()
    newer = _assignment(user_id=user_id)
    older = _assignment(user_id=user_id)
    plan = _plan(subscription_id=newer.subscription_id)

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        return_value=[(newer, plan), (older, plan)],
    ), caplog.at_level(logging.WARNING):
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=user_id,
                expected_type="EMPLOYER",
            )
        )

    assert summary.user_subscription_id == newer.user_subscription_id
    assert "Duplicate active subscriptions detected" in caplog.text


def test_current_subscription_endpoint_uses_same_selected_plan():
    user_id = uuid4()
    assignment = _assignment(user_id=user_id)
    plan = _plan(subscription_id=assignment.subscription_id, subscription_name="Premium Employer")

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionService._current_subscription_pair",
        new_callable=AsyncMock,
        return_value=(assignment, plan),
    ):
        current = asyncio.run(
            UserSubscriptionService.get_current_subscription(
                session=AsyncMock(),
                user_id=user_id,
            )
        )
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=user_id,
                expected_type="EMPLOYER",
            )
        )

    assert current.subscription_id == summary.subscription_id
    assert current.subscription.subscription_name == summary.subscription_name
    assert current.status == summary.status
    assert current.start_date == summary.start_date
    assert current.end_date == summary.end_date


def test_summary_does_not_expose_payment_or_internal_fields():
    user_id = uuid4()
    assignment = _assignment(
        user_id=user_id,
        razorpay_order_id="order_secret",
        razorpay_payment_id="pay_secret",
        transaction_reference="txn_secret",
        remarks="internal note",
    )
    plan = _plan(subscription_id=assignment.subscription_id)

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        return_value=[(assignment, plan)],
    ):
        summary = asyncio.run(
            UserSubscriptionService.get_current_subscription_summary(
                session=AsyncMock(),
                user_id=user_id,
                expected_type="EMPLOYER",
            )
        )

    dumped = summary.model_dump()
    assert "razorpay_order_id" not in dumped
    assert "razorpay_payment_id" not in dumped
    assert "transaction_reference" not in dumped
    assert "remarks" not in dumped


def test_authenticate_user_includes_subscription_compatibility_fields():
    user_id = uuid4()
    user = SimpleNamespace(
        user_id=user_id,
        email="employer@example.com",
        user_status="ACTIVE",
        roles=[SimpleNamespace(role_name="Employer", role_code="ROLE_EMPLOYER")],
    )
    assignment = _assignment(user_id=user_id)
    plan = _plan(subscription_id=assignment.subscription_id, subscription_name="Premium Employer")

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        new_callable=AsyncMock,
        return_value=user,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.list_current_subscription_candidates",
        new_callable=AsyncMock,
        return_value=[(assignment, plan)],
    ):
        result = asyncio.run(
            AuthService.authenticate_user(
                session=AsyncMock(),
                login=SimpleNamespace(email="employer@example.com"),
            )
        )

    assert result["role"] == "EMPLOYER"
    assert result["subscription"]["subscription_name"] == "Premium Employer"
    assert result["subscription_name"] == "Premium Employer"
    assert result["plan_name"] == "Premium Employer"


def test_user_profile_includes_no_active_plan_compatibility_fields():
    user = SimpleNamespace(
        user_id=uuid4(),
        first_name="Gopi",
        last_name="Kiran",
        email="gopi@example.com",
        mobile_number=None,
        user_status="ACTIVE",
        email_verified=True,
        mobile_verified=False,
        roles=[SimpleNamespace(role_code="ROLE_EMPLOYER")],
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
        created_by=None,
        updated_by=None,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: user)
        )
    )

    with patch(
        "app.service.authentication.users.UserSubscriptionService.get_current_subscription_summary",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = asyncio.run(
            UserService.get_user_profile(
                session=session,
                email=user.email,
            )
        )

    assert result["role"] == "EMPLOYER"
    assert result["subscription"] is None
    assert result["subscription_name"] == "No Active Plan"
    assert result["plan_name"] == "No Active Plan"
