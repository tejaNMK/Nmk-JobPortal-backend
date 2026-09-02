from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.utc import utc_now_naive


def _zone_or_fixed(name: str, offset_hours: float):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        hours = int(offset_hours)
        minutes = int((offset_hours - hours) * 60)
        return timezone(timedelta(hours=hours, minutes=minutes))


POSTED_DATE_DISPLAY_TZ = _zone_or_fixed("America/Los_Angeles", -8)
APPLICATION_DEADLINE_INPUT_TZ = _zone_or_fixed("Asia/Kolkata", 5.5)


def posted_display_date(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_date = value.astimezone(POSTED_DATE_DISPLAY_TZ).date()
    return datetime.combine(local_date, time.min, tzinfo=timezone.utc)


def normalize_deadline_to_utc_naive(deadline: datetime | date | None) -> datetime | None:
    if deadline is None:
        return None
    if isinstance(deadline, datetime):
        deadline_dt = deadline
    else:
        deadline_dt = datetime.combine(deadline, time.min)

    if deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=APPLICATION_DEADLINE_INPUT_TZ)

    return deadline_dt.astimezone(timezone.utc).replace(tzinfo=None)
