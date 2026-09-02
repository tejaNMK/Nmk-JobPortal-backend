from datetime import date, datetime, timedelta, tzinfo
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.service.notification_service import NotificationService
from app.service.super_admin.analytics_service import SuperAdminAnalyticsService
from app.utils.date_range import normalize_date_range


class FixedKeyTimezone(tzinfo):
    def __init__(self, key, offset_hours=0, offset_minutes=0):
        self.key = key
        self._offset = timedelta(hours=offset_hours, minutes=offset_minutes)

    def utcoffset(self, dt):
        return self._offset

    def dst(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return self.key


class NewYorkMarch2026Timezone(tzinfo):
    key = "America/New_York"

    def utcoffset(self, dt):
        if dt and dt.replace(tzinfo=None) >= datetime(2026, 3, 8, 2, 0):
            return timedelta(hours=-4)
        return timedelta(hours=-5)

    def dst(self, dt):
        return (
            timedelta(hours=1)
            if self.utcoffset(dt) == timedelta(hours=-4)
            else timedelta(0)
        )

    def tzname(self, dt):
        return self.key


def test_date_range_defaults_to_current_month(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 31, 12, 0, tzinfo=tz)

    monkeypatch.setattr("app.utils.date_range.datetime", FixedDateTime)
    monkeypatch.setattr(
        "app.utils.date_range._load_timezone",
        lambda timezone_name=None: FixedKeyTimezone("Asia/Kolkata", 5, 30),
    )

    result = normalize_date_range(timezone_name="Asia/Kolkata")

    assert result.from_date == date(2026, 7, 1)
    assert result.to_date == date(2026, 7, 31)
    assert result.timezone == "Asia/Kolkata"
    assert result.utc_start.isoformat() == "2026-06-30T18:30:00+00:00"
    assert result.utc_end_exclusive.isoformat() == "2026-07-31T18:30:00+00:00"


def test_date_range_rejects_partial_reversed_future_and_bad_timezone(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 31, 12, 0, tzinfo=tz)

    monkeypatch.setattr("app.utils.date_range.datetime", FixedDateTime)

    with pytest.raises(HTTPException) as partial:
        normalize_date_range(from_date="2026-07-01")
    assert partial.value.status_code == 422

    with pytest.raises(HTTPException) as reversed_range:
        normalize_date_range(from_date="2026-07-31", to_date="2026-07-01")
    assert reversed_range.value.status_code == 422

    with pytest.raises(HTTPException) as future:
        normalize_date_range(from_date="2026-08-01", to_date="2026-08-02")
    assert future.value.status_code == 422

    with pytest.raises(HTTPException) as bad_tz:
        normalize_date_range(
            from_date="2026-07-01",
            to_date="2026-07-31",
            timezone_name="Mars/Base",
        )
    assert bad_tz.value.status_code == 422


def test_date_range_handles_dst_exclusive_end(monkeypatch):
    monkeypatch.setattr(
        "app.utils.date_range._load_timezone",
        lambda timezone_name=None: NewYorkMarch2026Timezone(),
    )
    result = normalize_date_range(
        from_date="2026-03-07",
        to_date="2026-03-09",
        timezone_name="America/New_York",
    )

    assert result.utc_start.isoformat() == "2026-03-07T05:00:00+00:00"
    assert result.utc_end_exclusive.isoformat() == "2026-03-10T04:00:00+00:00"


def test_trend_items_zero_fill_daily_and_monthly():
    daily_range = normalize_date_range(
        from_date="2026-07-01",
        to_date="2026-07-03",
        timezone_name="UTC",
    )
    daily_rows = [SimpleNamespace(month="2026-07-02", count=4)]

    assert [
        item.model_dump()
        for item in SuperAdminAnalyticsService._trend_items(daily_rows, daily_range)
    ] == [
        {"month": "2026-07-01", "count": 0},
        {"month": "2026-07-02", "count": 4},
        {"month": "2026-07-03", "count": 0},
    ]

    monthly_range = normalize_date_range(
        from_date="2026-01-01",
        to_date="2026-07-31",
        timezone_name="UTC",
    )
    monthly_rows = [SimpleNamespace(month="2026-03", count=2)]

    items = SuperAdminAnalyticsService._trend_items(monthly_rows, monthly_range)

    assert items[0].model_dump() == {"month": "2026-01", "count": 0}
    assert items[2].model_dump() == {"month": "2026-03", "count": 2}
    assert items[-1].model_dump() == {"month": "2026-07", "count": 0}


@pytest.mark.asyncio
async def test_create_for_super_admins_fans_out_to_active_admins(monkeypatch):
    async def fake_get_admins(*, session):
        return ["admin-1", "admin-2"]

    captured = {}

    async def fake_bulk(*, session, notifications, commit):
        captured["notifications"] = notifications
        captured["commit"] = commit
        return len(notifications)

    monkeypatch.setattr(
        "app.service.notification_service.NotificationRepo.get_active_super_admin_user_ids",
        fake_get_admins,
    )
    monkeypatch.setattr(
        "app.service.notification_service.NotificationRepo.create_notifications_bulk",
        fake_bulk,
    )
    monkeypatch.setattr(
        "app.service.notification_service.Notification",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    count = await NotificationService.create_for_super_admins(
        None,
        notification_type="SYSTEM_ALERT",
        title="Alert",
        message="Something needs attention.",
        entity_type="system",
        target_route="/super-admin/logs",
        event_key="system:test",
        commit=True,
    )

    assert count == 2
    assert captured["commit"] is True
    assert {n.recipient_user_id for n in captured["notifications"]} == {
        "admin-1",
        "admin-2",
    }
    assert all(n.recipient_role == "ROLE_SUPER_ADMIN" for n in captured["notifications"])
    assert all(n.event_key == "system:test" for n in captured["notifications"])
