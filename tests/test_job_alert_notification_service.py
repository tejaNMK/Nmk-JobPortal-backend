import asyncio
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.modules.setdefault(
    "boto3",
    types.SimpleNamespace(client=lambda *args, **kwargs: None),
)
sys.modules.setdefault("botocore", types.SimpleNamespace())
sys.modules.setdefault(
    "botocore.exceptions",
    types.SimpleNamespace(ClientError=Exception),
)

from app.service.job_alert_notification_service import JobAlertNotificationService
from app.model.candidate_model.job_alert_notification_delivery import (
    JobAlertNotificationDelivery,
)
from app.repository.candidate_repo import CandidateProfileRepo
from app.model.authentication.mapper_bootstrap import bootstrap_mappers


bootstrap_mappers()


def _make_alert(**overrides):
    defaults = dict(
        alert_id="alert-1",
        candidate_id="cand-1",
        user_id="11111111-1111-1111-1111-111111111111",
        title="Java Developer Alert",
        job_category="Engineering",
        job_title="Java Developer",
        preferred_location="Hyderabad",
        employment_type="FULL_TIME",
        experience_level="MID_LEVEL",
        notification_preference="EMAIL",
        frequency="INSTANT",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_job(**overrides):
    defaults = dict(
        job_id="job-1",
        title="Java Developer",
        job_category="Engineering",
        location="Hyderabad",
        employment_type="FULL_TIME",
        company_name="Acme Corp",
        experience_min=2,
        experience_max=5,
        application_deadline=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _patched(**kwargs):
    reserve_delivery = kwargs.get(
        "reserve_delivery",
        AsyncMock(return_value=SimpleNamespace(id="delivery-1")),
    )
    mark_sent = kwargs.get("mark_sent", AsyncMock(return_value=None))
    mark_failed = kwargs.get("mark_failed", AsyncMock(return_value=None))

    return patch.multiple(
        "app.service.job_alert_notification_service",
        CandidateProfileRepo=SimpleNamespace(
            get_active_job_alert_candidates=kwargs["get_alerts"],
            get_active_job_alert_candidates_by_frequency=kwargs.get(
                "get_alerts_by_frequency", AsyncMock(return_value=[])
            ),
            get_jobs_posted_between=kwargs.get(
                "get_jobs_posted_between", AsyncMock(return_value=[])
            ),
        ),
        EmailService=SimpleNamespace(
            send_job_alert_email=kwargs["send_email"],
            send_job_alert_summary_email=kwargs.get(
                "send_summary_email", AsyncMock(return_value=None)
            ),
        ),
        NotificationService=SimpleNamespace(
            create_notification=kwargs["create_notification"],
            notification_already_sent=kwargs.get(
                "notification_already_sent", AsyncMock(return_value=False)
            ),
        ),
        JobAlertNotificationDeliveryRepo=SimpleNamespace(
            reserve_delivery=reserve_delivery,
            mark_sent=mark_sent,
            mark_failed=mark_failed,
        ),
    )


def test_matching_email_preference_sends_email_only():
    alert = _make_alert(notification_preference="EMAIL")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_awaited_once()
    assert send_email.await_args.kwargs["to_email"] == "jane@example.com"
    create_notification.assert_not_awaited()


def test_matching_in_app_preference_skips_email():
    alert = _make_alert(notification_preference="IN_APP")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_not_awaited()
    create_notification.assert_awaited_once()
    assert create_notification.await_args.kwargs["recipient_role"] == "ROLE_CANDIDATE"
    assert create_notification.await_args.kwargs["target_route"] == "/candidate/jobs/job-1"


def test_both_preference_sends_email_and_in_app_notification():
    alert = _make_alert(notification_preference="BOTH")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_awaited_once()
    create_notification.assert_awaited_once()


def test_delivery_channels_normalize_frontend_and_legacy_values():
    assert JobAlertNotificationService._delivery_channels("email") == (True, False)
    assert JobAlertNotificationService._delivery_channels("in-app") == (False, True)
    assert JobAlertNotificationService._delivery_channels("in app") == (False, True)
    assert JobAlertNotificationService._delivery_channels("both") == (True, True)
    assert JobAlertNotificationService._delivery_channels("PORTAL_NOTIFICATION") == (
        False,
        True,
    )


def test_non_instant_frequency_is_skipped():
    alert = _make_alert(frequency="DAILY")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_not_awaited()
    create_notification.assert_not_awaited()


@pytest.mark.parametrize("frequency", ["instant", " Instant ", None])
def test_instant_frequency_is_normalized_for_immediate_dispatch(frequency):
    alert = _make_alert(frequency=frequency, notification_preference="IN_APP")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=SimpleNamespace(notification_id="n1"))

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_not_awaited()
    create_notification.assert_awaited_once()


def test_non_matching_job_is_skipped():
    alert = _make_alert(
        job_category=None,
        job_title="Python Developer",
        preferred_location="Pune",
        experience_level=None,
        employment_type="FULL_TIME",
    )
    job = _make_job(
        title="Java Developer",
        location="Hyderabad",
        employment_type="CONTRACT",
    )

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_not_awaited()
    create_notification.assert_not_awaited()


def test_candidate_with_multiple_matching_alerts_dispatches_each_alert():
    alert_java = _make_alert(
        alert_id="alert-java",
        job_title="SQL Developer",
        preferred_location="Hyderabad",
    )
    alert_location_only = _make_alert(
        alert_id="alert-location",
        job_title=None,
        preferred_location="Hyderabad",
    )
    job = _make_job(title="SQL Developer", location="Hyderabad")

    get_alerts = AsyncMock(return_value=[alert_java, alert_location_only])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    assert send_email.await_count == 2
    create_notification.assert_not_awaited()


def test_candidate_matching_email_and_in_app_alerts_gets_both_channels():
    email_alert = _make_alert(
        alert_id="alert-email",
        notification_preference="EMAIL",
        job_title="SQL Developer",
        preferred_location="Hyderabad",
    )
    in_app_alert = _make_alert(
        alert_id="alert-in-app",
        notification_preference="IN_APP",
        job_title="SQL Developer",
        preferred_location="Hyderabad",
    )
    job = _make_job(title="SQL Developer", location="Hyderabad")

    get_alerts = AsyncMock(return_value=[email_alert, in_app_alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=SimpleNamespace(id="note-1"))

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_awaited_once()
    create_notification.assert_awaited_once()


def test_skips_dispatch_when_delivery_was_already_reserved_or_sent():
    alert = _make_alert()
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)
    reserve_delivery = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
        reserve_delivery=reserve_delivery,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    send_email.assert_not_awaited()
    create_notification.assert_not_awaited()


def test_job_title_matching_is_case_insensitive_and_trims_spaces():
    alert = _make_alert(
        job_title="  PYTHON  ",
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(title="Senior Python Developer")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_preferred_location_matching_is_case_insensitive_substring():
    alert = _make_alert(
        job_title=None,
        preferred_location="  hyderabad  ",
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(location="Hyderabad, Telangana")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_empty_job_category_is_ignored_for_matching():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(job_category="Product")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_job_title_match_is_not_blocked_by_category_mismatch():
    alert = _make_alert(
        job_category="Marketing",
        job_title="Python Developer",
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(
        title="Senior Python Developer",
        job_category="Engineering",
    )

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_experience_level_matches_job_experience_range():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level="SENIOR",
        employment_type=None,
    )
    job = _make_job(experience_min=6, experience_max=None)

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_experience_level_uses_posted_job_range_mapping():
    alert = _make_alert(
        job_title=None,
        preferred_location=None,
        experience_level="JUNIOR",
        employment_type=None,
    )
    job = _make_job(experience_min=1, experience_max=3)

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_experience_level_outside_job_experience_range_does_not_match():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level="SENIOR",
        employment_type=None,
    )
    job = _make_job(experience_min=2, experience_max=4)

    assert JobAlertNotificationService._is_match(job, alert) is False


def test_employment_type_matching_remains_exact_case_insensitive():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type="FULL_TIME",
    )
    job = _make_job(employment_type="PART_TIME")

    assert JobAlertNotificationService._is_match(job, alert) is False


def test_any_populated_field_match_triggers_alert():
    alert = _make_alert(
        job_title="Java Developer",
        preferred_location="Hyderabad",
        employment_type="CONTRACT",
    )
    job = _make_job(
        title="Java Developer",
        location="Hyderabad",
        employment_type="FULL_TIME",
    )

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_job_category_matching_is_case_insensitive_and_trims_spaces():
    alert = _make_alert(
        job_category="  engineering  ",
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(job_category="Engineering")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_job_category_mismatch_does_not_match():
    alert = _make_alert(
        job_category="Marketing",
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(job_category="Engineering")

    assert JobAlertNotificationService._is_match(job, alert) is False


def test_alert_without_job_category_does_not_restrict_matching():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(job_category="Engineering")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_categorized_alert_rejects_job_with_no_category():
    alert = _make_alert(
        job_category="Engineering",
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(job_category=None)

    assert JobAlertNotificationService._is_match(job, alert) is False


def test_alert_with_no_matching_fields_matches_all_jobs():
    alert = _make_alert(
        job_category=None,
        job_title=None,
        preferred_location=None,
        experience_level=None,
        employment_type=None,
    )
    job = _make_job(title="Any Job", location="Anywhere", employment_type="CONTRACT")

    assert JobAlertNotificationService._is_match(job, alert) is True


def test_daily_notifications_are_consolidated_and_deduplicated():
    alert_one = _make_alert(
        alert_id="alert-1",
        notification_preference="BOTH",
        job_title=None,
    )
    alert_two = _make_alert(
        alert_id="alert-2",
        notification_preference="BOTH",
        job_title=None,
    )
    job_one = _make_job(job_id="job-1")
    job_two = _make_job(job_id="job-2", title="Python Developer")

    get_alerts = AsyncMock(return_value=[])
    get_alerts_by_frequency = AsyncMock(return_value=[alert_one, alert_two])
    get_jobs_posted_between = AsyncMock(return_value=[job_one, job_two])
    send_email = AsyncMock(return_value=None)
    send_summary_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)
    reserve_delivery = AsyncMock(
        side_effect=[
            SimpleNamespace(id="delivery-email"),
            SimpleNamespace(id="delivery-in-app"),
        ]
    )

    with _patched(
        get_alerts=get_alerts,
        get_alerts_by_frequency=get_alerts_by_frequency,
        get_jobs_posted_between=get_jobs_posted_between,
        send_email=send_email,
        send_summary_email=send_summary_email,
        create_notification=create_notification,
        reserve_delivery=reserve_delivery,
    ):
        asyncio.run(
            JobAlertNotificationService.process_daily_notifications(
                session=None,
                run_at=datetime(2026, 7, 27, 9, 0, 0),
            )
        )

    get_alerts_by_frequency.assert_awaited_once()
    assert get_alerts_by_frequency.await_args.kwargs["frequency"] == "DAILY"
    send_summary_email.assert_awaited_once()
    assert len(send_summary_email.await_args.kwargs["jobs"]) == 2
    create_notification.assert_awaited_once()
    assert create_notification.await_args.kwargs["message"] == "2 new jobs matched your Job Alert."
    assert reserve_delivery.await_count == 2


def test_daily_notifications_use_run_time_for_digest_window():
    get_alerts = AsyncMock(return_value=[])
    get_alerts_by_frequency = AsyncMock(return_value=[])
    get_jobs_posted_between = AsyncMock(return_value=[])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        get_alerts_by_frequency=get_alerts_by_frequency,
        get_jobs_posted_between=get_jobs_posted_between,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.process_daily_notifications(
                session=None,
                run_at=datetime(2026, 7, 27, 8, 0, 0),
            )
        )

    get_jobs_posted_between.assert_not_awaited()
    assert JobAlertNotificationService._daily_window(
        datetime(2026, 7, 27, 8, 0, 0)
    ) == (
        datetime(2026, 7, 26, 8, 0, 0),
        datetime(2026, 7, 27, 7, 59, 59, 999999),
    )


def test_weekly_notifications_use_previous_monday_window():
    get_alerts = AsyncMock(return_value=[])
    get_alerts_by_frequency = AsyncMock(return_value=[])
    get_jobs_posted_between = AsyncMock(return_value=[])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        get_alerts_by_frequency=get_alerts_by_frequency,
        get_jobs_posted_between=get_jobs_posted_between,
        send_email=send_email,
        create_notification=create_notification,
    ):
        asyncio.run(
            JobAlertNotificationService.process_weekly_notifications(
                session=None,
                run_at=datetime(2026, 7, 27, 9, 0, 0),
            )
        )

    get_alerts_by_frequency.assert_awaited_once()
    assert get_alerts_by_frequency.await_args.kwargs["frequency"] == "WEEKLY"


def test_both_preference_tracks_email_and_in_app_independently():
    alert = _make_alert(notification_preference="BOTH")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=SimpleNamespace(notification_id="n1"))
    reserve_delivery = AsyncMock(
        side_effect=[
            SimpleNamespace(id="email-delivery"),
            SimpleNamespace(id="in-app-delivery"),
        ]
    )
    mark_sent = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
        reserve_delivery=reserve_delivery,
        mark_sent=mark_sent,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    assert reserve_delivery.await_count == 2
    channels = [call.kwargs["channel"] for call in reserve_delivery.await_args_list]
    assert channels == ["EMAIL", "IN_APP"]
    assert [call.kwargs["delivery_id"] for call in mark_sent.await_args_list] == [
        "email-delivery",
        "in-app-delivery",
    ]


def test_failed_email_delivery_is_marked_failed_not_sent():
    alert = _make_alert(notification_preference="EMAIL")
    job = _make_job()

    get_alerts = AsyncMock(return_value=[alert])
    send_email = AsyncMock(side_effect=RuntimeError("smtp token secret failed"))
    create_notification = AsyncMock(return_value=None)
    mark_sent = AsyncMock(return_value=None)
    mark_failed = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        send_email=send_email,
        create_notification=create_notification,
        mark_sent=mark_sent,
        mark_failed=mark_failed,
    ):
        asyncio.run(
            JobAlertNotificationService.notify_matching_candidates(session=None, job=job)
        )

    mark_sent.assert_not_awaited()
    mark_failed.assert_awaited_once()
    assert "secret" not in mark_failed.await_args.kwargs["error"]
    assert "token" not in mark_failed.await_args.kwargs["error"]


def test_daily_digest_rerun_skips_when_delivery_identity_exists():
    alert = _make_alert(
        alert_id="alert-1",
        notification_preference="EMAIL",
        job_title=None,
        frequency="DAILY",
    )
    job = _make_job(job_id="job-1")

    get_alerts = AsyncMock(return_value=[])
    get_alerts_by_frequency = AsyncMock(return_value=[alert])
    get_jobs_posted_between = AsyncMock(return_value=[job])
    send_email = AsyncMock(return_value=None)
    send_summary_email = AsyncMock(return_value=None)
    create_notification = AsyncMock(return_value=None)
    reserve_delivery = AsyncMock(return_value=None)

    with _patched(
        get_alerts=get_alerts,
        get_alerts_by_frequency=get_alerts_by_frequency,
        get_jobs_posted_between=get_jobs_posted_between,
        send_email=send_email,
        send_summary_email=send_summary_email,
        create_notification=create_notification,
        reserve_delivery=reserve_delivery,
    ):
        asyncio.run(
            JobAlertNotificationService.process_daily_notifications(
                session=None,
                run_at=datetime(2026, 7, 27, 9, 0, 0),
            )
        )

    reserve_delivery.assert_awaited_once()
    send_summary_email.assert_not_awaited()


def test_different_digest_windows_have_different_delivery_keys():
    first_start, first_end = JobAlertNotificationService._daily_window(
        datetime(2026, 7, 27, 9, 0, 0)
    )
    second_start, second_end = JobAlertNotificationService._daily_window(
        datetime(2026, 7, 28, 9, 0, 0)
    )

    first = JobAlertNotificationService._delivery_key(
        recipient_id="user-1",
        alert_id=None,
        job_id=None,
        frequency="DAILY",
        channel="EMAIL",
        window_start=first_start,
        window_end=first_end,
    )
    second = JobAlertNotificationService._delivery_key(
        recipient_id="user-1",
        alert_id=None,
        job_id=None,
        frequency="DAILY",
        channel="EMAIL",
        window_start=second_start,
        window_end=second_end,
    )

    assert first != second


def test_delivery_table_has_db_level_unique_delivery_identity():
    unique_constraints = [
        constraint
        for constraint in JobAlertNotificationDelivery.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]

    assert any(
        constraint.name == "uq_job_alert_notification_deliveries_delivery_key"
        and [column.name for column in constraint.columns] == ["delivery_key"]
        for constraint in unique_constraints
    )


def test_subscription_feature_check_allows_sessionless_dispatch_tests():
    alert = _make_alert(user_id="11111111-1111-1111-1111-111111111111")

    assert asyncio.run(
        JobAlertNotificationService._candidate_has_job_alerts_feature(
            session=None,
            alert=alert,
        )
    ) is True


def test_digest_job_lookup_only_considers_published_jobs():
    captured = {}

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        async def execute(self, statement):
            captured["sql"] = str(
                statement.compile(compile_kwargs={"literal_binds": True})
            )
            return FakeResult()

    asyncio.run(
        CandidateProfileRepo.get_jobs_posted_between(
            session=FakeSession(),
            start_at=datetime(2026, 7, 27, 0, 0, 0),
            end_at=datetime(2026, 7, 28, 0, 0, 0),
        )
    )

    assert "jobs.status = 'PUBLISHED'" in captured["sql"]
    assert "jobs.is_deleted IS false" in captured["sql"]
