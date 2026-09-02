from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from dateutil import tz
from dateutil.zoneinfo import get_zonefile_instance


TIMEZONE_VALIDATION_MESSAGE = "Timezone must be a valid IANA timezone name."


@lru_cache(maxsize=1)
def get_timezone_options() -> tuple[dict[str, str], ...]:
    names = sorted(
        name
        for name in _available_timezone_names()
        if _is_frontend_timezone_name(name)
    )
    if "UTC" not in names:
        names.insert(0, "UTC")
    return tuple({"value": name, "label": name} for name in names)


@lru_cache(maxsize=1)
def get_supported_timezone_names() -> frozenset[str]:
    return frozenset(option["value"] for option in get_timezone_options())


def validate_iana_timezone_name(value: str | None) -> str | None:
    if value is None:
        return value

    normalized = value.strip()
    if not normalized:
        return None

    if normalized not in get_supported_timezone_names():
        raise ValueError(TIMEZONE_VALIDATION_MESSAGE)

    if not _timezone_can_load(normalized):
        raise ValueError(TIMEZONE_VALIDATION_MESSAGE)

    return normalized


def _available_timezone_names() -> set[str]:
    names = set(available_timezones())
    if names:
        return names
    return set(get_zonefile_instance().zones.keys())


def _is_frontend_timezone_name(name: str) -> bool:
    if name.startswith(("posix/", "right/")):
        return False
    if name.upper() != "UTC" and "/" not in name:
        return False
    if not _timezone_can_load(name):
        return False
    return True


def _timezone_can_load(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except ZoneInfoNotFoundError:
        return tz.gettz(name) is not None
