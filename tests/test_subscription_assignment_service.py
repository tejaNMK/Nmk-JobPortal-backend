import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException

from app.schema.subscription.user_subscription import (
    AssignSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeSubscriptionRequest,
    RenewSubscriptionRequest,
    SelfSubscribeRequest,
    SubscriptionActionRequest,
)
from app.schema.subscription.subscription import SubscriptionUpdate
from app.service.subscription.subscription_bootstrap_service import (
    SubscriptionBootstrapService,
)
from app.service.subscription.subscription_service import SubscriptionService
from app.service.subscription.user_subscription_service import UserSubscriptionService
from app.service.subscription.subscription_validator import SubscriptionValidator
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository


bootstrap_mappers()


def _plan(
    subscription_id=None,
    duration_days=30,
    active=True,
    price=Decimal("19.00"),
):
    return SimpleNamespace(
        subscription_id=subscription_id or uuid4(),
        subscription_type="CANDIDATE",
        duration_days=duration_days,
        is_active=active,
        price=price,
        currency="USD",
        max_published_jobs=10,
        max_job_alerts=None,
        max_resume_uploads=5,
        is_featured=False,
        feature_flags={"resume_builder": True},
        model_dump=lambda: {"subscription_id": str(subscription_id or uuid4())},
    )


def _user_subscription(**overrides):
    now = utc_now_naive()
    values = {
        "user_subscription_id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "role": "CANDIDATE",
        "start_date": now,
        "end_date": now + timedelta(days=30),
        "status": "ACTIVE",
        "payment_status": "PAID",
        "price_paid": Decimal("19.00"),
        "discount_amount": Decimal("0.00"),
        "currency": "USD",
        "auto_renew": False,
        "transaction_reference": None,
        "invoice_number": None,
        "remarks": None,
        "assigned_by": None,
        "cancelled_at": None,
        "created_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user_with_role(role_code):
    return SimpleNamespace(roles=[SimpleNamespace(role_code=role_code)])


def _compiled_sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


def test_assign_subscription_rejects_existing_active_subscription():
    user_id = uuid4()
    subscription_id = uuid4()
    request = AssignSubscriptionRequest(
        user_id=user_id,
        subscription_id=subscription_id,
        role="CANDIDATE",
    )
    active = _user_subscription(user_id=user_id, subscription_id=subscription_id)

    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=_plan(subscription_id),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=active,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.assign_subscription(
                    session=AsyncMock(),
                    request=request,
                    assigned_by=uuid4(),
                )
            )

    assert exc.value.status_code == 409


def test_get_latest_subscription_limits_to_one_row():
    user_id = uuid4()
    latest = _user_subscription(user_id=user_id)
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: latest)
        )
    )

    result = asyncio.run(
        UserSubscriptionRepository.get_latest_subscription(
            session=session,
            user_id=user_id,
            role="CANDIDATE",
        )
    )

    sql = _compiled_sql(session.execute.await_args.args[0])
    assert result == latest
    assert "ORDER BY user_subscriptions.created_at DESC" in sql
    assert "LIMIT 1" in sql
    assert "upper(user_subscriptions.role) = 'CANDIDATE'" in sql


def test_assign_subscription_checks_existing_active_subscription_for_same_role_only():
    user_id = uuid4()
    subscription_id = uuid4()
    plan = _plan(subscription_id)
    plan.subscription_type = "EMPLOYER"
    request = AssignSubscriptionRequest(
        user_id=user_id,
        subscription_id=subscription_id,
        role="EMPLOYER",
    )
    created = _user_subscription(
        user_id=user_id,
        subscription_id=subscription_id,
        role="EMPLOYER",
    )

    async def _create(session, user_subscription):
        return created

    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_EMPLOYER"),
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_active, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.create",
        new=AsyncMock(side_effect=_create),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            UserSubscriptionService.assign_subscription(
                session=AsyncMock(),
                request=request,
                assigned_by=uuid4(),
            )
        )

    assert result.role == "EMPLOYER"
    assert get_active.await_args.kwargs["role"] == "EMPLOYER"


def test_assign_subscription_rejects_plan_for_different_role():
    user_id = uuid4()
    subscription_id = uuid4()
    plan = _plan(subscription_id)
    plan.subscription_type = "EMPLOYER"
    request = AssignSubscriptionRequest(
        user_id=user_id,
        subscription_id=subscription_id,
        role="CANDIDATE",
    )

    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.assign_subscription(
                    session=AsyncMock(),
                    request=request,
                    assigned_by=uuid4(),
                )
            )

    assert exc.value.status_code == 400
    assert "EMPLOYER plans cannot be assigned to CANDIDATE users" in exc.value.detail


def test_assign_subscription_rejects_invalid_payment_status():
    try:
        AssignSubscriptionRequest(
            user_id=uuid4(),
            subscription_id=uuid4(),
            role="CANDIDATE",
            payment_status="SUCCESS_FROM_BROWSER",
        )
    except ValueError as exc:
        assert "Invalid payment_status" in str(exc)
    else:
        raise AssertionError("Expected payment status validation to fail")


def test_self_subscribe_uses_plan_role_and_authenticated_user():
    user_id = uuid4()
    subscription_id = uuid4()
    plan = _plan(subscription_id, price=Decimal("0.00"))
    created = _user_subscription(
        user_id=user_id,
        subscription_id=subscription_id,
        role="CANDIDATE",
        payment_status="FREE",
        price_paid=Decimal("0.00"),
    )

    async def _create(session, user_subscription):
        assert user_subscription.user_id == user_id
        assert user_subscription.role == "CANDIDATE"
        assert user_subscription.subscription_id == subscription_id
        assert user_subscription.payment_status == "FREE"
        return created

    with patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.create",
        new=AsyncMock(side_effect=_create),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            UserSubscriptionService.subscribe_self(
                session=AsyncMock(),
                user_id=user_id,
                request=SelfSubscribeRequest(subscription_id=subscription_id),
            )
        )

    assert result.user_id == user_id
    assert result.role == "CANDIDATE"
    assert result.payment_status == "FREE"


def test_self_subscribe_rejects_paid_plan_without_razorpay_checkout():
    user_id = uuid4()
    subscription_id = uuid4()
    plan = _plan(subscription_id, price=Decimal("19.00"))

    with patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.subscribe_self(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=SelfSubscribeRequest(subscription_id=subscription_id),
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Paid plans must be purchased through Razorpay checkout."


def test_self_subscribe_rejects_plan_when_user_lacks_plan_role():
    user_id = uuid4()
    subscription_id = uuid4()
    plan = _plan(subscription_id)
    plan.subscription_type = "EMPLOYER"

    with patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.subscribe_self(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=SelfSubscribeRequest(subscription_id=subscription_id),
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "User does not have EMPLOYER role."


def test_employer_self_subscribe_rejects_candidate_plan():
    user_id = uuid4()
    subscription_id = uuid4()
    candidate_plan = _plan(subscription_id)
    candidate_plan.subscription_type = "CANDIDATE"

    with patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=candidate_plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_EMPLOYER"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.subscribe_self(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=SelfSubscribeRequest(subscription_id=subscription_id),
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "User does not have CANDIDATE role."


def test_renew_subscription_extends_active_end_date_and_resets_usage():
    user_id = uuid4()
    subscription_id = uuid4()
    old_end = utc_now_naive() + timedelta(days=5)
    user_subscription = _user_subscription(
        user_id=user_id,
        subscription_id=subscription_id,
        end_date=old_end,
    )
    plan = _plan(subscription_id, duration_days=30)

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=user_subscription,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.reset_usage",
        new_callable=AsyncMock,
    ) as reset_usage, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ) as add_history:
        result = asyncio.run(
            UserSubscriptionService.renew_subscription(
                session=AsyncMock(),
                user_id=user_id,
                request=RenewSubscriptionRequest(),
                performed_by=uuid4(),
            )
        )

    assert result.status == "ACTIVE"
    assert result.end_date == old_end + timedelta(days=30)
    reset_usage.assert_awaited_once()
    add_history.assert_awaited_once()


def test_renew_subscription_rejects_plan_for_different_role():
    user_id = uuid4()
    current_plan_id = uuid4()
    employer_plan_id = uuid4()
    user_subscription = _user_subscription(
        user_id=user_id,
        subscription_id=current_plan_id,
        role="CANDIDATE",
    )
    plan = _plan(employer_plan_id)
    plan.subscription_type = "EMPLOYER"

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=user_subscription,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.renew_subscription(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=RenewSubscriptionRequest(subscription_id=employer_plan_id),
                    performed_by=uuid4(),
                )
            )

    assert exc.value.status_code == 400
    assert "EMPLOYER plans cannot be assigned to CANDIDATE users" in exc.value.detail


def test_cancel_subscription_marks_cancelled_and_records_history():
    user_id = uuid4()
    user_subscription = _user_subscription(user_id=user_id)

    async def _cancel(session, user_subscription):
        user_subscription.status = "CANCELLED"
        return user_subscription

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=user_subscription,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.cancel_subscription",
        new=AsyncMock(side_effect=_cancel),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ) as add_history, patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=_plan(user_subscription.subscription_id),
    ):
        result = asyncio.run(
            UserSubscriptionService.cancel_subscription(
                session=AsyncMock(),
                user_id=user_id,
                request=CancelSubscriptionRequest(remarks="manual cancel"),
                performed_by=uuid4(),
            )
        )

    assert result.status == "CANCELLED"
    assert result.cancelled_at is not None
    add_history.assert_awaited_once()


def test_cancel_subscription_targets_explicit_subscription_id():
    user_id = uuid4()
    target = _user_subscription(user_id=user_id, role="EMPLOYER")
    unrelated_active = _user_subscription(user_id=user_id, role="CANDIDATE")

    async def _cancel(session, user_subscription):
        user_subscription.status = "CANCELLED"
        return user_subscription

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=target,
    ) as get_by_id, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=unrelated_active,
    ) as get_active, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.cancel_subscription",
        new=AsyncMock(side_effect=_cancel),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=_plan(target.subscription_id),
    ):
        result = asyncio.run(
            UserSubscriptionService.cancel_subscription(
                session=AsyncMock(),
                user_id=user_id,
                user_subscription_id=target.user_subscription_id,
                request=CancelSubscriptionRequest(remarks="manual cancel"),
                performed_by=uuid4(),
            )
        )

    assert result.user_subscription_id == target.user_subscription_id
    get_by_id.assert_awaited_once()
    get_active.assert_not_awaited()


def test_expire_if_needed_marks_expired_and_commits():
    expired = _user_subscription(end_date=utc_now_naive() - timedelta(days=1))
    session = AsyncMock()
    session.add = MagicMock()

    result = asyncio.run(
        UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=expired,
            performed_by=uuid4(),
        )
    )

    assert result.status == "EXPIRED"
    session.add.assert_called()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(expired)


def test_assign_default_subscription_returns_existing_active_without_duplicate():
    user_id = uuid4()
    existing = _user_subscription(user_id=user_id)
    session = AsyncMock()

    with patch(
        "app.service.subscription.subscription_bootstrap_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=existing,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionBootstrapService.ensure_default_plan",
        new_callable=AsyncMock,
    ) as ensure_default_plan:
        result = asyncio.run(
            SubscriptionBootstrapService.ensure_user_subscription(
                session=session,
                user_id=user_id,
                role="CANDIDATE",
            )
        )

    assert result is existing
    ensure_default_plan.assert_not_awaited()
    session.add.assert_not_called()


def test_ensure_default_plan_creates_enabled_feature_plan():
    session = AsyncMock()
    session.add = MagicMock()
    subscription_id = uuid4()

    async def _flush():
        added_plan = session.add.call_args.args[0]
        added_plan.subscription_id = subscription_id

    session.flush.side_effect = _flush

    with patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionRepository.get_default",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionRepository.exists_by_name",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionRepository.clear_default_for_type",
        new_callable=AsyncMock,
    ) as clear_default:
        plan = asyncio.run(
            SubscriptionBootstrapService.ensure_default_plan(
                session=session,
                role="CANDIDATE",
                features={"candidate_profile": True, "job_search": True},
            )
        )

    assert plan.subscription_name == "Default Candidate Plan"
    assert plan.subscription_type == "CANDIDATE"
    assert plan.is_active is True
    assert plan.is_default is True
    assert plan.price == Decimal("0.00")
    assert plan.max_resume_uploads == 5
    assert plan.feature_flags["candidate_profile"] is True
    assert plan.feature_flags["job_search"] is True
    clear_default.assert_awaited_once()


def test_bootstrap_defaults_updates_system_default_settings():
    session = AsyncMock()
    session.add = MagicMock()
    candidate_plan = _plan(uuid4())
    candidate_plan.subscription_type = "CANDIDATE"
    employer_plan = _plan(uuid4())
    employer_plan.subscription_type = "EMPLOYER"
    settings = SimpleNamespace(
        candidate_default_subscription_plan=None,
        employer_default_subscription_plan=None,
        default_subscription_plan=None,
    )

    with patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionBootstrapService.ensure_default_plan",
        new_callable=AsyncMock,
        side_effect=[candidate_plan, employer_plan],
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=settings,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionBootstrapService.backfill_missing_user_subscriptions",
        new_callable=AsyncMock,
        return_value=0,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.commit_rollback",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            SubscriptionBootstrapService.bootstrap_defaults_and_assignments(
                session=session,
            )
        )

    assert settings.candidate_default_subscription_plan == str(candidate_plan.subscription_id)
    assert settings.employer_default_subscription_plan == str(employer_plan.subscription_id)
    assert settings.default_subscription_plan == str(candidate_plan.subscription_id)
    assert result["features_discovered"] > 0


def test_subscription_update_setting_default_clears_existing_default():
    subscription_id = uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    plan = _plan(subscription_id)
    plan.subscription_name = "Gold Candidate"
    plan.subscription_type = "CANDIDATE"
    plan.description = None
    plan.is_default = False
    plan.created_at = utc_now_naive()
    plan.updated_at = utc_now_naive()
    settings = SimpleNamespace(
        candidate_default_subscription_plan=None,
        employer_default_subscription_plan=None,
        default_subscription_plan=None,
    )

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.clear_default_for_type",
        new_callable=AsyncMock,
    ) as clear_default, patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ), patch(
        "app.service.subscription.subscription_service.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=settings,
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=session,
                subscription_id=subscription_id,
                request=SubscriptionUpdate(is_default=True),
            )
        )

    assert result.is_default is True
    clear_default.assert_awaited_once()
    assert settings.candidate_default_subscription_plan == str(subscription_id)
    assert settings.default_subscription_plan == str(subscription_id)


def test_subscription_update_rejects_type_change_when_plan_has_assignments():
    subscription_id = uuid4()
    plan = _plan(subscription_id)
    plan.subscription_name = "Candidate Gold"
    plan.subscription_type = "CANDIDATE"
    plan.description = None
    plan.is_default = False
    plan.created_at = utc_now_naive()
    plan.updated_at = utc_now_naive()

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.count_user_assignments",
        new_callable=AsyncMock,
        return_value=1,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                SubscriptionService.update(
                    session=AsyncMock(),
                    subscription_id=subscription_id,
                    request=SubscriptionUpdate(subscription_type="EMPLOYER"),
                )
            )

    assert exc.value.status_code == 400
    assert "cannot be changed while the plan is assigned" in exc.value.detail


def test_configured_system_default_plan_is_used_for_assignment():
    configured_plan_id = uuid4()
    configured_plan = _plan(configured_plan_id)
    configured_plan.subscription_type = "CANDIDATE"
    session = AsyncMock()

    with patch(
        "app.service.subscription.subscription_bootstrap_service.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            candidate_default_subscription_plan=str(configured_plan_id),
            employer_default_subscription_plan=None,
            default_subscription_plan=None,
        ),
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=configured_plan,
    ), patch(
        "app.service.subscription.subscription_bootstrap_service.SubscriptionBootstrapService.ensure_default_plan",
        new_callable=AsyncMock,
    ) as ensure_default_plan:
        plan = asyncio.run(
            SubscriptionBootstrapService.get_assignment_default_plan(
                session=session,
                role="CANDIDATE",
            )
        )

    assert plan is configured_plan
    ensure_default_plan.assert_not_awaited()


def test_subscription_validator_assigns_role_default_when_missing_active_subscription():
    user_id = uuid4()
    assigned = _user_subscription(user_id=user_id, role="CANDIDATE")

    with patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_active, patch(
        "app.service.subscription.subscription_validator.SubscriptionBootstrapService.ensure_user_subscription",
        new_callable=AsyncMock,
        return_value=assigned,
    ) as ensure_user_subscription:
        result = asyncio.run(
            SubscriptionValidator(
                session=AsyncMock(),
                user_id=user_id,
                role="CANDIDATE",
            ).validate_active_subscription()
        )

    assert result is assigned
    get_active.assert_awaited_once()
    assert get_active.await_args.kwargs["role"] == "CANDIDATE"
    ensure_user_subscription.assert_awaited_once()
    assert ensure_user_subscription.await_args.kwargs["role"] == "CANDIDATE"


def test_subscription_validator_allows_resume_builder_feature():
    user_id = uuid4()
    active = _user_subscription(user_id=user_id, role="CANDIDATE")
    plan = _plan(active.subscription_id)
    plan.feature_flags = {"resume_builder": True}

    with patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=active,
    ), patch(
        "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        allowed = asyncio.run(
            SubscriptionValidator(
                session=AsyncMock(),
                user_id=user_id,
                role="CANDIDATE",
            ).has_feature("resume_builder")
        )

    assert allowed is True


def test_subscription_validator_blocks_resume_builder_when_disabled():
    user_id = uuid4()
    active = _user_subscription(user_id=user_id, role="CANDIDATE")
    plan = _plan(active.subscription_id)
    plan.feature_flags = {"resume_builder": False}

    with patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=active,
    ), patch(
        "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        allowed = asyncio.run(
            SubscriptionValidator(
                session=AsyncMock(),
                user_id=user_id,
                role="CANDIDATE",
            ).has_feature("resume_builder")
        )

    assert allowed is False


def test_subscription_validator_rejects_mismatched_plan_role():
    user_id = uuid4()
    active = _user_subscription(user_id=user_id, role="CANDIDATE")
    plan = _plan(active.subscription_id)
    plan.subscription_type = "EMPLOYER"

    with patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=active,
    ), patch(
        "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                SubscriptionValidator(
                    session=AsyncMock(),
                    user_id=user_id,
                    role="CANDIDATE",
                ).has_feature("resume_builder")
            )

    assert exc.value.status_code == 400
    assert "EMPLOYER plans cannot be assigned to CANDIDATE users" in exc.value.detail


def test_subscription_validator_blocks_saved_jobs_usage_that_exceeds_limit():
    user_id = uuid4()
    active = _user_subscription(user_id=user_id, role="CANDIDATE")
    plan = _plan(active.subscription_id)
    plan.feature_flags = {"saved_jobs_limit": 5}
    usage = SimpleNamespace(used_count=4)

    with patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=active,
    ), patch(
        "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_usage",
        new_callable=AsyncMock,
        return_value=usage,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                SubscriptionValidator(
                    session=AsyncMock(),
                    user_id=user_id,
                    role="CANDIDATE",
                ).consume_limit("saved_jobs_limit", amount=2)
            )

    assert exc.value.status_code == 403
    assert "Subscription limit reached" in exc.value.detail


def test_change_subscription_updates_plan_resets_usage_and_records_history():
    user_id = uuid4()
    new_plan_id = uuid4()
    current = _user_subscription(user_id=user_id)
    new_plan = _plan(new_plan_id)
    new_plan.subscription_type = "CANDIDATE"

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=current,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=new_plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.reset_usage",
        new_callable=AsyncMock,
    ) as reset_usage, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ) as add_history:
        result = asyncio.run(
            UserSubscriptionService.change_subscription(
                session=AsyncMock(),
                user_id=user_id,
                request=ChangeSubscriptionRequest(subscription_id=new_plan_id),
                action="UPGRADED",
                performed_by=uuid4(),
            )
        )

    assert result.subscription_id == new_plan_id
    reset_usage.assert_awaited_once()
    history = add_history.await_args.kwargs["history"]
    assert history.action == "UPGRADED"


def test_change_subscription_creates_new_subscription_when_latest_is_cancelled():
    user_id = uuid4()
    new_plan_id = uuid4()
    cancelled = _user_subscription(user_id=user_id, status="CANCELLED")
    new_plan = _plan(new_plan_id)
    new_plan.subscription_type = "CANDIDATE"

    async def _create(session, user_subscription, **kwargs):
        return user_subscription

    with patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_latest_subscription",
        new_callable=AsyncMock,
        return_value=cancelled,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=new_plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.create",
        new=AsyncMock(side_effect=_create),
    ) as create, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.update",
        new_callable=AsyncMock,
    ) as update, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.reset_usage",
        new_callable=AsyncMock,
    ) as reset_usage, patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ) as add_history:
        result = asyncio.run(
            UserSubscriptionService.change_subscription(
                session=AsyncMock(),
                user_id=user_id,
                request=ChangeSubscriptionRequest(subscription_id=new_plan_id),
                action="UPGRADED",
                performed_by=user_id,
            )
        )

    assert result.status == "ACTIVE"
    assert result.subscription_id == new_plan_id
    assert result.user_subscription_id != cancelled.user_subscription_id
    create.assert_awaited_once()
    update.assert_not_awaited()
    reset_usage.assert_not_awaited()
    history = add_history.await_args.kwargs["history"]
    assert history.action == "UPGRADED"
    assert history.old_start_date == cancelled.start_date
    assert history.old_end_date == cancelled.end_date


def test_change_subscription_rejects_plan_when_user_lacks_target_role():
    user_id = uuid4()
    new_plan_id = uuid4()
    current = _user_subscription(user_id=user_id, role="CANDIDATE")
    new_plan = _plan(new_plan_id)
    new_plan.subscription_type = "EMPLOYER"

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=current,
    ), patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=new_plan,
    ), patch(
        "app.service.subscription.user_subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_user_with_role("ROLE_CANDIDATE"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.change_subscription(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=ChangeSubscriptionRequest(subscription_id=new_plan_id),
                    action="UPGRADED",
                    performed_by=uuid4(),
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "User does not have EMPLOYER role."


def test_suspend_subscription_records_status_history():
    user_id = uuid4()
    current = _user_subscription(user_id=user_id)

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=current,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.add_history",
        new_callable=AsyncMock,
    ) as add_history, patch(
        "app.service.subscription.user_subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=_plan(current.subscription_id),
    ):
        result = asyncio.run(
            UserSubscriptionService.update_status(
                session=AsyncMock(),
                user_id=user_id,
                request=SubscriptionActionRequest(remarks="policy hold"),
                status="SUSPENDED",
                action="SUSPENDED",
                performed_by=uuid4(),
            )
        )

    assert result.status == "SUSPENDED"
    history = add_history.await_args.kwargs["history"]
    assert history.action == "SUSPENDED"


def test_cancelled_subscription_cannot_be_resumed_by_invalid_transition():
    user_id = uuid4()
    current = _user_subscription(user_id=user_id, status="CANCELLED")

    with patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_latest_subscription",
        new_callable=AsyncMock,
        return_value=current,
    ), patch(
        "app.service.subscription.user_subscription_service.UserSubscriptionRepository.get_active_subscription",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                UserSubscriptionService.update_status(
                    session=AsyncMock(),
                    user_id=user_id,
                    request=SubscriptionActionRequest(remarks="resume"),
                    status="ACTIVE",
                    action="RESUMED",
                    performed_by=uuid4(),
                )
            )

    assert exc.value.status_code == 400
    assert "Cannot change subscription" in exc.value.detail
