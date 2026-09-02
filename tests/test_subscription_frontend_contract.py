import asyncio
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from app.utils.utc import utc_now_naive

from app.schema.subscription.subscription import SubscriptionCreate, SubscriptionUpdate
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.service.subscription.subscription_service import SubscriptionService
from app.model.authentication.mapper_bootstrap import bootstrap_mappers


bootstrap_mappers()


def _plan(**overrides):
    data = {
        "subscription_id": uuid4(),
        "subscription_name": "Candidate Basic",
        "subscription_type": "CANDIDATE",
        "description": "Starter plan for active job seekers.",
        "price": Decimal("0"),
        "currency": "USD",
        "duration_days": 30,
        "billing_cycle": "Monthly",
        "display_order": 1,
        "max_published_jobs": None,
        "max_job_alerts": None,
        "max_resume_uploads": None,
        "max_candidate_searches": None,
        "feature_flags": {},
        "is_featured": False,
        "is_popular": False,
        "is_active": True,
        "is_default": False,
        "created_at": utc_now_naive(),
        "updated_at": utc_now_naive(),
        "created_by": None,
        "updated_by": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class _FakeScalars:
    def all(self):
        return []


class _FakeExecuteResult:
    def scalars(self):
        return _FakeScalars()


class _CapturingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeExecuteResult()


def test_subscription_get_all_query_does_not_distinct_json_feature_flags():
    session = _CapturingSession()

    asyncio.run(
        SubscriptionRepository.get_all(
            session=session,
            subscription_type="CANDIDATE",
            status="active",
        )
    )

    assert "DISTINCT" not in str(session.statement).upper()


def test_subscription_create_does_not_auto_grant_unrelated_features():
    created_plan = _plan()

    async def _create(session, subscription):
        created_plan.feature_flags = subscription.feature_flags
        return created_plan

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.exists_by_name",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.create",
        new=AsyncMock(side_effect=_create),
    ):
        result = asyncio.run(
            SubscriptionService.create(
                session=AsyncMock(),
                request=SubscriptionCreate(
                    subscription_name="Candidate Basic",
                    subscription_type="CANDIDATE",
                    price=Decimal("0"),
                    currency="USD",
                    duration_days=30,
                    billing_cycle="Monthly",
                    display_order=1,
                ),
            )
        )

    assert result.features == {}
    assert result.feature_flags == {}


def test_subscription_response_hides_generated_feature_flags():
    result = asyncio.run(
        SubscriptionService._response(
            session=AsyncMock(),
            subscription=_plan(
                feature_flags={
                    "candidateSearch": True,
                    "saved_jobs_limit": 30,
                    "module_schema_auth": True,
                    "api_get_openapi_json_openapi": True,
                },
            ),
        )
    )

    assert result.saved_jobs_limit == 30
    assert result.features == {
        "candidate_search": True,
    }
    assert result.feature_flags == {
        "candidate_search": True,
    }


def test_subscription_create_rejects_negative_price_and_limits():
    try:
        SubscriptionCreate(
            subscription_name="Unsafe Plan",
            subscription_type="CANDIDATE",
            price=Decimal("-1.00"),
            currency="USD",
            duration_days=30,
            billing_cycle="Monthly",
            display_order=1,
            max_resume_uploads=-2,
            saved_jobs_limit=-1,
            candidate_invitations_per_week=-1,
        )
    except ValueError as exc:
        message = str(exc)
        assert "price" in message
        assert "max_resume_uploads" in message
        assert "saved_jobs_limit" in message
        assert "candidate_invitations_per_week" in message
    else:
        raise AssertionError("Expected negative price and limit validation to fail")


def test_subscription_update_accepts_frontend_nested_features():
    plan = _plan()

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=AsyncMock(),
                subscription_id=plan.subscription_id,
                request=SubscriptionUpdate(
                    features={
                        "resume_features": {
                            "resume_upload": True,
                            "resume_builder": False,
                        },
                        "job_applications": {
                            "max_job_applications": 10,
                            "unlimited_job_applications": False,
                        },
                    },
                    popular_plan=True,
                ),
            )
        )

    assert result.is_popular is True
    assert result.popular_plan is True
    assert result.features == {
        "resume_builder": False,
    }


def test_available_plans_for_candidate_user_fetches_active_candidate_plans():
    user_id = uuid4()
    captured = {}
    plan = _plan(subscription_type="CANDIDATE", is_active=True)

    async def fake_get_all(session, **kwargs):
        captured.update(kwargs)
        return [plan]

    with patch(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            roles=[SimpleNamespace(role_code="ROLE_CANDIDATE")]
        ),
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        new=AsyncMock(side_effect=fake_get_all),
    ):
        result = asyncio.run(
            SubscriptionService.get_available_for_user(
                session=AsyncMock(),
                user_id=user_id,
            )
        )

    assert captured["subscription_type"] == "CANDIDATE"
    assert captured["status"] == "active"
    assert result[0].subscription_type == "CANDIDATE"


def test_available_plans_for_employer_user_fetches_active_employer_plans():
    captured = {}
    plan = _plan(subscription_type="EMPLOYER", is_active=True)

    async def fake_get_all(session, **kwargs):
        captured.update(kwargs)
        return [plan]

    with patch(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            roles=[SimpleNamespace(role_code="ROLE_RECRUITER")]
        ),
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        new=AsyncMock(side_effect=fake_get_all),
    ):
        result = asyncio.run(
            SubscriptionService.get_available_for_user(
                session=AsyncMock(),
                user_id=uuid4(),
            )
        )

    assert captured["subscription_type"] == "EMPLOYER"
    assert captured["status"] == "active"
    assert result[0].subscription_type == "EMPLOYER"


def test_available_plans_for_employer_user_filters_mixed_repository_rows():
    candidate_plan = _plan(subscription_type="CANDIDATE", is_active=True)
    employer_plan = _plan(
        subscription_name="Employer Basic",
        subscription_type="EMPLOYER",
        is_active=True,
    )

    with patch(
        "app.service.subscription.subscription_service.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            roles=[SimpleNamespace(role_code="ROLE_EMPLOYER")]
        ),
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_all",
        new_callable=AsyncMock,
        return_value=[candidate_plan, employer_plan],
    ):
        result = asyncio.run(
            SubscriptionService.get_available_for_user(
                session=AsyncMock(),
                user_id=uuid4(),
            )
        )

    assert [plan.subscription_type for plan in result] == ["EMPLOYER"]


def test_subscription_create_accepts_frontend_status_and_flat_toggles():
    created_plan = _plan()

    async def _create(session, subscription):
        created_plan.is_active = subscription.is_active
        created_plan.max_published_jobs = subscription.max_published_jobs
        created_plan.max_job_alerts = subscription.max_job_alerts
        created_plan.max_resume_uploads = subscription.max_resume_uploads
        created_plan.feature_flags = subscription.feature_flags
        return created_plan

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.exists_by_name",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.create",
        new=AsyncMock(side_effect=_create),
    ):
        result = asyncio.run(
            SubscriptionService.create(
                session=AsyncMock(),
                request=SubscriptionCreate(
                    subscription_name="Candidate Basic",
                    subscription_type="CANDIDATE",
                    price=Decimal("0"),
                    currency="USD",
                    duration_days=30,
                    billing_cycle="Monthly",
                    display_order=1,
                    status="Inactive",
                    max_published_jobs=6,
                    max_job_alerts=3,
                    max_resume_uploads=2,
                    resume_builder=False,
                    saved_jobs_limit=15,
                    candidate_invitations=True,
                    candidate_invitations_per_week=4,
                ),
            )
        )

    assert result.is_active is False
    assert result.status == "Inactive"
    assert result.max_published_jobs == 6
    assert result.max_job_alerts == 3
    assert result.max_resume_uploads == 2
    assert result.saved_jobs_limit == 15
    assert result.candidate_invitations is True
    assert result.candidate_invitations_per_week == 4
    assert result.features == {
        "candidate_invitations": True,
        "resume_builder": False,
    }


def test_subscription_update_preserves_existing_features_when_flat_toggle_changes():
    plan = _plan(
        feature_flags={
            "resume_builder": True,
            "saved_jobs": True,
        }
    )

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=AsyncMock(),
                subscription_id=plan.subscription_id,
                    request=SubscriptionUpdate(
                        status=False,
                        job_alerts=True,
                    ),
            )
        )

    assert result.is_active is False
    assert result.status == "Inactive"
    assert result.features == {
        "resume_builder": True,
        "saved_jobs": True,
        "job_alerts": True,
    }


def test_subscription_update_preserves_existing_features_when_nested_toggle_changes():
    plan = _plan(
        feature_flags={
            "resume_builder": True,
            "saved_jobs_limit": 25,
        }
    )

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=AsyncMock(),
                subscription_id=plan.subscription_id,
                request=SubscriptionUpdate(
                    features={
                        "resume_features": {
                            "resume_upload": False,
                        },
                    },
                ),
            )
        )

    assert result.saved_jobs_limit == 25
    assert result.features == {
        "resume_builder": True,
    }


def test_subscription_update_ignores_removed_frontend_toggle_names():
    plan = _plan()

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=AsyncMock(),
                subscription_id=plan.subscription_id,
                request=SubscriptionUpdate(
                    status="Active",
                    resumeUpload=True,
                    **{
                        "AI Resume Review": True,
                        "Priority Customer Support": False,
                    },
                ),
            )
        )

    assert result.is_active is True
    assert result.features == {}


def test_subscription_update_accepts_full_frontend_payload_without_overwriting_readonly_fields():
    original_id = uuid4()
    original_created_at = utc_now_naive()
    plan = _plan(
        subscription_id=original_id,
        subscription_name="Candidate Basic",
        is_popular=False,
        created_at=original_created_at,
        feature_flags={
            "resume_builder": True,
        },
    )

    async def _update(session, subscription):
        return subscription

    with patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.get_by_id",
        new_callable=AsyncMock,
        return_value=plan,
    ), patch(
        "app.service.subscription.subscription_service.SubscriptionRepository.update",
        new=AsyncMock(side_effect=_update),
    ):
        result = asyncio.run(
            SubscriptionService.update(
                session=AsyncMock(),
                subscription_id=original_id,
                request=SubscriptionUpdate(
                    subscriptionId=str(uuid4()),
                    subscriptionName="Candidate Pro",
                    popularPlan=True,
                    createdAt=utc_now_naive().isoformat(),
                    updatedAt=utc_now_naive().isoformat(),
                    features={
                        "resume_upload": False,
                    },
                ),
            )
        )

    assert result.subscription_id == original_id
    assert result.subscription_name == "Candidate Pro"
    assert result.created_at == original_created_at
    assert result.popular_plan is True
    assert result.features == {
        "resume_builder": True,
    }
