from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.model.activity_log import ActivityLog
from app.service.super_admin.activity_log_service import ActivityLogService
from app.utils.date_range import (
    normalize_date_range,
    normalize_datetime_for_db,
    normalize_to_utc,
)


def test_activity_log_model_default_is_aware_utc():
    created_at = ActivityLog.model_fields["created_at"].default_factory()

    assert ActivityLog.__table__.c.created_at.type.timezone is True
    assert created_at.tzinfo is not None
    assert created_at.utcoffset().total_seconds() == 0


def test_normalize_to_utc_treats_naive_historical_values_as_utc():
    value = datetime(2026, 7, 31, 0, 8, 0)

    normalized = normalize_to_utc(value)

    assert normalized.isoformat() == "2026-07-31T00:08:00+00:00"


def test_normalize_datetime_for_db_converts_aware_to_naive_utc():
    aware_ist = datetime(
        2026,
        7,
        31,
        5,
        30,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    naive_utc = datetime(2026, 7, 31, 0, 0)

    assert normalize_datetime_for_db(aware_ist) == naive_utc
    assert normalize_datetime_for_db(naive_utc) == naive_utc
    assert normalize_datetime_for_db(None) is None


def test_activity_log_date_range_uses_full_local_day_exclusive_end(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 31, 12, 0, tzinfo=tz)

    monkeypatch.setattr("app.utils.date_range.datetime", FixedDateTime)

    # Use the real UTC fallback path here; non-UTC DST behavior is covered
    # by the shared date-range tests.
    result = normalize_date_range(
        from_date="2026-07-31",
        to_date="2026-07-31",
        timezone_name="UTC",
    )

    assert result.utc_start.isoformat() == "2026-07-31T00:00:00+00:00"
    assert result.utc_end_exclusive.isoformat() == "2026-08-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_activity_log_service_serializes_created_at_as_utc(monkeypatch):
    log_id = uuid4()
    naive_created_at = datetime(2026, 7, 31, 0, 8, 0)
    log = SimpleNamespace(
        id=log_id,
        actor_id=None,
        actor_role="ROLE_CANDIDATE",
        action="PROFILE_UPDATED",
        description="Candidate social links updated",
        entity_type="Candidate",
        entity_id="candidate-1",
        target_entity_name="Candidate One",
        ip_address=None,
        metadata_=None,
        created_at=naive_created_at,
    )

    async def fake_list_logs(**kwargs):
        return [(log, None)], 1

    monkeypatch.setattr(
        "app.service.super_admin.activity_log_service.ActivityLogRepository.list_logs",
        fake_list_logs,
    )

    response = await ActivityLogService.list_logs(
        session=None,
        page=1,
        page_size=10,
    )

    item = response.items[0]
    assert item.activity_log_id == log_id
    assert item.created_at.isoformat() == "2026-07-31T00:08:00+00:00"
    assert item.timestamp.isoformat() == "2026-07-31T00:08:00+00:00"
