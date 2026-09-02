from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.constants.activity_constants import ACTIVITY_MESSAGE_VERBS, ActivityType
from app.model.employer_model.job_posting_audit import JobPostingAudit


_STATUS_LABELS = {
    "ACTIVE": "Active",
    "ARCHIVED": "Archived",
    "CLOSED": "Closed",
    "DRAFT": "Draft",
    "PUBLISHED": "Published",
}
_TITLE_ACRONYMS = {"API", "AWS", "CSS", "DBA", "HTML", "HTTP", "IT", "JDBC", "JS", "QA", "SQL", "UI", "UX"}


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _parse_metadata(message: Optional[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if not message or "=" not in message:
        return metadata

    for part in message.split(";"):
        key, separator, value = part.partition("=")
        if not separator:
            continue
        clean_key = key.strip()
        clean_value = _clean_text(value)
        if clean_key and clean_value:
            metadata[clean_key] = clean_value
    return metadata


def _humanize_title(value: Optional[str]) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None
    words = []
    for word in text.split():
        upper_word = word.upper()
        words.append(upper_word if upper_word in _TITLE_ACRONYMS else word.capitalize())
    return " ".join(words)


def _humanize_status(value: Optional[str]) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None
    return _STATUS_LABELS.get(text.upper(), text.replace("_", " ").title())


def _activity_type(value: Optional[str]) -> ActivityType:
    try:
        return ActivityType(value or "")
    except ValueError:
        return ActivityType.ACTIVITY_RECORDED


def build_recent_activity(
    audit: JobPostingAudit,
    *,
    job_title: Optional[str] = None,
) -> dict[str, Any]:
    metadata = _parse_metadata(audit.message)
    activity_type = _activity_type(audit.event_type)
    title = _humanize_title(job_title) or _humanize_title(metadata.get("title"))
    status = _humanize_status(metadata.get("status"))
    label = ACTIVITY_MESSAGE_VERBS[activity_type]
    message = f'{label} "{title}"' if title else label
    created_at: datetime = audit.created_at
    job_id = _clean_text(audit.job_id)

    return {
        "id": str(audit.audit_id),
        "activity_id": str(audit.audit_id),
        "activity_type": activity_type.value,
        "message": message,
        "title": title,
        "status": status,
        "created_at": created_at,
        "happened_at": created_at,
        "description": message,
        "job_id": job_id,
    }


def unpack_activity_row(row):
    try:
        audit, job = row
        return audit, job
    except (TypeError, ValueError):
        return row, None
