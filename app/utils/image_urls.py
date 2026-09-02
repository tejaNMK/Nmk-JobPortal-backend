from __future__ import annotations

import logging
from pathlib import PurePosixPath
from urllib.parse import quote

from app.service import s3_service


logger = logging.getLogger(__name__)

PROFILE_IMAGES_PREFIX = "profile-images/"


def resolve_profile_image_url(stored_value: str | None) -> str | None:
    if not stored_value:
        return None

    value = stored_value.strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    if not value.startswith(PROFILE_IMAGES_PREFIX):
        return None

    path = PurePosixPath(value)
    parts = path.parts
    if len(parts) != 3 or parts[0] != "profile-images":
        return None

    user_id, filename = parts[1], parts[2]
    if not user_id or not filename or filename in {".", ".."}:
        return None

    try:
        safe_key = s3_service.build_profile_image_key(user_id, filename)
    except Exception:
        return None

    if safe_key != value:
        return None

    return f"/profile-images/{quote(user_id, safe='')}/{quote(filename, safe='')}"
