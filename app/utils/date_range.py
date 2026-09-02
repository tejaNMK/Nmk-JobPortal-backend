from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException


@dataclass(frozen=True)
class NormalizedDateRange:
    from_date: date
    to_date: date
    timezone: str
    utc_start: datetime
    utc_end_exclusive: datetime

    def as_response(self) -> dict[str, str]:
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "timezone": self.timezone,
        }

    @property
    def start_date(self) -> date:
        return self.from_date

    @property
    def end_date(self) -> date:
        return self.to_date

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    @property
    def grouping(self) -> str:
        if self.days <= 31:
            return "daily"
        if self.days <= 180:
            return "weekly"
        return "monthly"


def _parse_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be a valid YYYY-MM-DD date.",
        ) from exc


class _NamedTimezone(tzinfo):
    def __init__(self, wrapped: tzinfo, key: str):
        self._wrapped = wrapped
        self.key = key

    def utcoffset(self, dt):
        return self._wrapped.utcoffset(dt)

    def dst(self, dt):
        return self._wrapped.dst(dt) or timedelta(0)

    def tzname(self, dt):
        return self._wrapped.tzname(dt)


def _load_timezone(timezone_name: str | None) -> tzinfo:
    normalized = (timezone_name or "UTC").strip() or "UTC"
    if normalized.upper() == "UTC":
        return _NamedTimezone(timezone.utc, "UTC")
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail="timezone must be a valid IANA timezone name.",
        ) from exc


def normalize_date_range(
    *,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
    timezone_name: str | None = None,
) -> NormalizedDateRange:
    tz = _load_timezone(timezone_name)
    today = datetime.now(tz).date()

    if isinstance(from_date, date):
        parsed_from = from_date
    else:
        parsed_from = _parse_date(from_date, "from_date")

    if isinstance(to_date, date):
        parsed_to = to_date
    else:
        parsed_to = _parse_date(to_date, "to_date")

    if (parsed_from is None) != (parsed_to is None):
        raise HTTPException(
            status_code=422,
            detail="from_date and to_date must be supplied together.",
        )

    if parsed_from is None or parsed_to is None:
        parsed_from = today.replace(day=1)
        parsed_to = today

    if parsed_to < parsed_from:
        raise HTTPException(
            status_code=422,
            detail="to_date cannot be earlier than from_date.",
        )

    if parsed_from > today or parsed_to > today:
        raise HTTPException(
            status_code=422,
            detail="Date ranges cannot include future dates.",
        )

    local_start = datetime.combine(parsed_from, time.min, tzinfo=tz)
    local_end = datetime.combine(parsed_to + timedelta(days=1), time.min, tzinfo=tz)

    return NormalizedDateRange(
        from_date=parsed_from,
        to_date=parsed_to,
        timezone=getattr(tz, "key", timezone_name or "UTC"),
        utc_start=local_start.astimezone(timezone.utc),
        utc_end_exclusive=local_end.astimezone(timezone.utc),
    )


def normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_datetime_for_db(value: datetime | None) -> datetime | None:
    """Return naive UTC for TIMESTAMP WITHOUT TIME ZONE column comparisons.

    Most existing project timestamp columns are PostgreSQL TIMESTAMP WITHOUT
    TIME ZONE and store UTC-naive values. asyncpg rejects comparisons between
    those columns and offset-aware Python datetimes, so repositories must
    normalize aware API bounds before building SQLAlchemy filters.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
