import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.candidate_schema import JobAlertUpdateSchema, JobAlertUpsertSchema
from app.constants.notification_constants import NotificationFrequency
from app.service.candidate_service import CandidateProfileService
from app.service.job_alert_notification_service import JobAlertNotificationService


def _valid_payload(**overrides):
    payload = {
        "title": "Engineering Alert",
        "job_category": "Engineering",
        "job_title": "Developer",
        "preferred_location": "Remote",
        "experience_level": "MID_LEVEL",
        "employment_type": "FULL_TIME",
        "notification_preference": "EMAIL",
        "frequency": "DAILY",
    }
    payload.update(overrides)
    return payload


def _make_alert(**overrides):
    defaults = dict(
        alert_id="alert-1",
        candidate_id="cand-1",
        user_id="11111111-1111-1111-1111-111111111111",
        title="Engineering Alert",
        job_category=None,
        job_title=None,
        preferred_location=None,
        employment_type=None,
        experience_level=None,
        notification_preference="EMAIL",
        frequency="DAILY",
        timezone="UTC",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_job(**overrides):
    defaults = dict(
        job_id="job-1",
        title="Developer",
        job_category="Engineering",
        location="Remote",
        employment_type="FULL_TIME",
        company_name="Acme",
        experience_min=1,
        experience_max=5,
        application_deadline=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _AllowingSubscriptionValidator:
    def __init__(self, *args, **kwargs):
        pass

    async def require_feature(self, feature_name):
        return None

    async def get_limit(self, limit_name):
        return None


def _patched(**kwargs):
    return patch.multiple(
        "app.service.job_alert_notification_service",
        CandidateProfileRepo=SimpleNamespace(
            get_active_job_alert_candidates=AsyncMock(return_value=[]),
            get_active_job_alert_candidates_by_frequency=kwargs[
                "get_alerts_by_frequency"
            ],
            get_jobs_posted_between=kwargs["get_jobs_posted_between"],
        ),
        EmailService=SimpleNamespace(
            send_job_alert_email=AsyncMock(return_value=None),
            send_job_alert_summary_email=kwargs["send_summary_email"],
        ),
        NotificationService=SimpleNamespace(
            create_notification=AsyncMock(return_value=None),
            notification_already_sent=AsyncMock(return_value=False),
        ),
        JobAlertNotificationDeliveryRepo=SimpleNamespace(
            reserve_delivery=kwargs.get(
                "reserve_delivery",
                AsyncMock(return_value=SimpleNamespace(id="delivery-1")),
            ),
            mark_sent=AsyncMock(return_value=None),
            mark_failed=AsyncMock(return_value=None),
        ),
        SubscriptionValidator=_AllowingSubscriptionValidator,
    )


def test_job_alert_schema_accepts_valid_iana_timezone():
    alert = JobAlertUpsertSchema(**_valid_payload(timezone="Europe/London"))

    assert alert.timezone == "Europe/London"


def test_job_alert_schema_rejects_invalid_timezone():
    try:
        JobAlertUpsertSchema(**_valid_payload(timezone="Mars/Olympus"))
    except ValidationError as exc:
        assert "Timezone must be a valid IANA timezone name" in str(exc)
    else:
        raise AssertionError("invalid timezone should be rejected")


def test_job_alert_schema_rejects_fixed_offset_timezone():
    try:
        JobAlertUpsertSchema(**_valid_payload(timezone="+05:30"))
    except ValidationError as exc:
        assert "Timezone must be a valid IANA timezone name" in str(exc)
    else:
        raise AssertionError("fixed offset timezone should be rejected")


def test_missing_timezone_remains_backward_compatible():
    alert = JobAlertUpsertSchema(**_valid_payload())

    assert alert.timezone is None


@pytest.mark.asyncio
async def test_create_job_alert_missing_timezone_stores_default_utc():
    user_id = uuid4()
    created_alert = _make_alert(
        alert_id="created-alert",
        timezone="UTC",
        is_active=True,
        created_at=datetime(2026, 7, 27, 2, 30),
    )
    create_alert = AsyncMock(return_value=created_alert)

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(candidate_id="cand-1"),
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator",
            _AllowingSubscriptionValidator,
        ),
        patch(
            "app.service.candidate_service.MasterDataService.validate_job_category",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_duplicate_job_alert",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.create_job_alert",
            create_alert,
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.service.candidate_service.JOB_ALERT_DEFAULT_TIMEZONE", "UTC"),
    ):
        result = await CandidateProfileService.create_job_alert(
            session=None,
            user_id=user_id,
            data=JobAlertUpsertSchema(**_valid_payload()),
        )

    assert create_alert.await_args.kwargs["timezone"] == "UTC"
    assert result.timezone == "UTC"


@pytest.mark.asyncio
async def test_update_legacy_job_alert_without_timezone_stores_default_utc():
    user_id = uuid4()
    existing_alert = _make_alert(timezone=None, is_active=True)
    updated_alert = _make_alert(
        timezone="UTC",
        title="Updated Alert",
        is_active=True,
        created_at=datetime(2026, 7, 27, 2, 30),
    )
    update_alert = AsyncMock(return_value=updated_alert)

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(candidate_id="cand-1"),
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator",
            _AllowingSubscriptionValidator,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_job_alert",
            new_callable=AsyncMock,
            return_value=existing_alert,
        ),
        patch(
            "app.service.candidate_service.MasterDataService.validate_job_category",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_duplicate_job_alert",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_job_alert",
            update_alert,
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.service.candidate_service.JOB_ALERT_DEFAULT_TIMEZONE", "UTC"),
    ):
        result = await CandidateProfileService.update_job_alert(
            session=None,
            user_id=user_id,
            alert_id="alert-1",
            data=JobAlertUpdateSchema(title="Updated Alert"),
        )

    assert update_alert.await_args.kwargs["timezone"] == "UTC"
    assert result.timezone == "UTC"


@pytest.mark.asyncio
async def test_update_job_alert_omitted_timezone_preserves_existing_timezone():
    user_id = uuid4()
    existing_alert = _make_alert(timezone="Asia/Kolkata", is_active=True)
    updated_alert = _make_alert(
        timezone="Asia/Kolkata",
        title="Updated Alert",
        is_active=True,
        created_at=datetime(2026, 7, 27, 2, 30),
    )
    update_alert = AsyncMock(return_value=updated_alert)

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(candidate_id="cand-1"),
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator",
            _AllowingSubscriptionValidator,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_job_alert",
            new_callable=AsyncMock,
            return_value=existing_alert,
        ),
        patch(
            "app.service.candidate_service.MasterDataService.validate_job_category",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_job_alert_by_title",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.find_duplicate_job_alert",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.update_job_alert",
            update_alert,
        ),
        patch(
            "app.service.candidate_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await CandidateProfileService.update_job_alert(
            session=None,
            user_id=user_id,
            alert_id="alert-1",
            data=JobAlertUpdateSchema(title="Updated Alert"),
        )

    assert "timezone" not in update_alert.await_args.kwargs
    assert result.timezone == "Asia/Kolkata"


def test_daily_due_digest_uses_asia_kolkata_local_window_converted_to_utc():
    alert = _make_alert(timezone="Asia/Kolkata")
    job = _make_job()
    get_alerts = AsyncMock(return_value=[alert])
    get_jobs = AsyncMock(return_value=[job])
    send_summary = AsyncMock(return_value=None)

    with _patched(
        get_alerts_by_frequency=get_alerts,
        get_jobs_posted_between=get_jobs,
        send_summary_email=send_summary,
    ):
        asyncio.run(
            JobAlertNotificationService.process_due_notifications(
                session=None,
                previous_run_at_utc=datetime(2026, 7, 27, 2, 15, tzinfo=UTC),
                run_at_utc=datetime(2026, 7, 27, 2, 30, tzinfo=UTC),
            )
        )

    get_jobs.assert_awaited()
    assert get_jobs.await_args.kwargs["start_at"] == datetime(
        2026, 7, 26, 2, 30, tzinfo=UTC
    )
    assert get_jobs.await_args.kwargs["end_at"] == datetime(
        2026, 7, 27, 2, 29, 59, 999999, tzinfo=UTC
    )
    send_summary.assert_awaited_once()


def test_daily_due_digest_uses_new_york_local_window_converted_to_utc():
    alert = _make_alert(timezone="America/New_York")
    job = _make_job()
    get_alerts = AsyncMock(return_value=[alert])
    get_jobs = AsyncMock(return_value=[job])
    send_summary = AsyncMock(return_value=None)

    with _patched(
        get_alerts_by_frequency=get_alerts,
        get_jobs_posted_between=get_jobs,
        send_summary_email=send_summary,
    ):
        asyncio.run(
            JobAlertNotificationService.process_due_notifications(
                session=None,
                previous_run_at_utc=datetime(2026, 7, 27, 11, 45, tzinfo=UTC),
                run_at_utc=datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
            )
        )

    assert get_jobs.await_args.kwargs["start_at"] == datetime(
        2026, 7, 26, 12, 0, tzinfo=UTC
    )
    assert get_jobs.await_args.kwargs["end_at"] == datetime(
        2026, 7, 27, 11, 59, 59, 999999, tzinfo=UTC
    )


def test_london_spring_forward_daily_window_is_not_assumed_24_hours():
    window = JobAlertNotificationService._due_digest_window_utc(
        frequency=NotificationFrequency.DAILY,
        local_previous_run_at=datetime(
            2026, 3, 29, 6, 45, tzinfo=JobAlertNotificationService._load_timezone("Europe/London")
        ),
        local_run_at=datetime(
            2026, 3, 29, 8, 0, tzinfo=JobAlertNotificationService._load_timezone("Europe/London")
        ),
    )

    assert window == (
        datetime(2026, 3, 28, 8, 0, tzinfo=UTC),
        datetime(2026, 3, 29, 6, 59, 59, 999999, tzinfo=UTC),
    )


def test_new_york_fall_back_daily_window_is_not_duplicated():
    window = JobAlertNotificationService._due_digest_window_utc(
        frequency=NotificationFrequency.DAILY,
        local_previous_run_at=datetime(
            2026, 11, 1, 7, 45, tzinfo=JobAlertNotificationService._load_timezone("America/New_York")
        ),
        local_run_at=datetime(
            2026, 11, 1, 8, 0, tzinfo=JobAlertNotificationService._load_timezone("America/New_York")
        ),
    )

    assert window == (
        datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 1, 12, 59, 59, 999999, tzinfo=UTC),
    )


def test_weekly_due_digest_uses_local_weekday_and_utc_window():
    alert = _make_alert(frequency="WEEKLY", timezone="Europe/London")
    job = _make_job()
    get_alerts = AsyncMock(side_effect=[[], [alert]])
    get_jobs = AsyncMock(return_value=[job])
    send_summary = AsyncMock(return_value=None)

    with _patched(
        get_alerts_by_frequency=get_alerts,
        get_jobs_posted_between=get_jobs,
        send_summary_email=send_summary,
    ):
        asyncio.run(
            JobAlertNotificationService.process_due_notifications(
                session=None,
                previous_run_at_utc=datetime(2026, 7, 27, 7, 45, tzinfo=UTC),
                run_at_utc=datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
            )
        )

    assert get_jobs.await_args.kwargs["start_at"] == datetime(
        2026, 7, 20, 8, 0, tzinfo=UTC
    )
    assert get_jobs.await_args.kwargs["end_at"] == datetime(
        2026, 7, 27, 7, 59, 59, 999999, tzinfo=UTC
    )


def test_multi_timezone_scheduler_run_only_processes_due_candidates():
    india = _make_alert(alert_id="india", timezone="Asia/Kolkata")
    new_york = _make_alert(alert_id="ny", timezone="America/New_York")
    job = _make_job()
    get_alerts = AsyncMock(return_value=[india, new_york])
    get_jobs = AsyncMock(return_value=[job])
    send_summary = AsyncMock(return_value=None)

    with _patched(
        get_alerts_by_frequency=get_alerts,
        get_jobs_posted_between=get_jobs,
        send_summary_email=send_summary,
    ):
        asyncio.run(
            JobAlertNotificationService.process_due_notifications(
                session=None,
                previous_run_at_utc=datetime(2026, 7, 27, 2, 15, tzinfo=UTC),
                run_at_utc=datetime(2026, 7, 27, 2, 30, tzinfo=UTC),
            )
        )

    assert send_summary.await_count == 1


def test_digest_delivery_key_includes_alert_channel_and_utc_window():
    key = JobAlertNotificationService._delivery_key(
        recipient_id="user-1",
        alert_id="alert-1",
        job_id=None,
        frequency="DAILY",
        channel="EMAIL",
        window_start=datetime(2026, 7, 26, 2, 30, tzinfo=UTC),
        window_end=datetime(2026, 7, 27, 2, 29, 59, 999999, tzinfo=UTC),
    )

    assert key == (
        "JOB_ALERT:DAILY:user-1:alert-1:"
        "2026-07-26T02:30:00+00:00:"
        "2026-07-27T02:29:59.999999+00:00:EMAIL"
    )
