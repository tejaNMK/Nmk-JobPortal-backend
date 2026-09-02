from datetime import datetime, timezone

from app.utils.job_time import normalize_deadline_to_utc_naive, posted_display_date


def test_posted_display_date_uses_pacific_business_date_at_utc_midnight():
    created_at = datetime(2026, 7, 24, 2, 30, tzinfo=timezone.utc)

    assert posted_display_date(created_at) == datetime(2026, 7, 23, 0, 0, tzinfo=timezone.utc)


def test_naive_application_deadline_is_interpreted_as_india_midnight():
    deadline = datetime(2026, 7, 29, 0, 0)

    assert normalize_deadline_to_utc_naive(deadline) == datetime(2026, 7, 28, 18, 30)
