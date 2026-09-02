import pytest
from pydantic import ValidationError

from app.candidate_schema import JobAlertUpdateSchema, JobAlertUpsertSchema


def _valid_job_alert_payload(**overrides):
    payload = {
        "title": "Python Alert",
        "job_category": "Software",
        "job_title": "Python Developer",
        "preferred_location": "Hyderabad",
        "experience_level": "MID_LEVEL",
        "employment_type": "FULL_TIME",
        "notification_preference": "EMAIL",
        "frequency": "DAILY",
    }
    payload.update(overrides)
    return payload


def test_create_missing_job_title_is_rejected():
    payload = _valid_job_alert_payload()
    payload.pop("job_title")

    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpsertSchema(**payload)

    assert "Job Title is required." in str(exc_info.value)


def test_create_blank_job_title_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpsertSchema(**_valid_job_alert_payload(job_title="   "))

    assert "Job Title is required." in str(exc_info.value)


def test_create_missing_title_is_rejected():
    payload = _valid_job_alert_payload()
    payload.pop("title")

    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpsertSchema(**payload)

    assert "Job Alert Title is required." in str(exc_info.value)


def test_create_blank_title_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpsertSchema(**_valid_job_alert_payload(title="   "))

    assert "Job Alert Title is required." in str(exc_info.value)


def test_create_missing_frequency_defaults_to_instant():
    payload = _valid_job_alert_payload()
    payload.pop("frequency")

    alert = JobAlertUpsertSchema(**payload)

    assert alert.frequency == "INSTANT"


def test_create_missing_job_category_is_allowed():
    payload = _valid_job_alert_payload()
    payload.pop("job_category")

    alert = JobAlertUpsertSchema(**payload)

    assert alert.job_category is None


def test_create_blank_job_category_is_normalized_to_none():
    alert = JobAlertUpsertSchema(**_valid_job_alert_payload(job_category="   "))

    assert alert.job_category is None


def test_job_alert_experience_accepts_posted_job_mapping_values():
    assert (
        JobAlertUpsertSchema(
            **_valid_job_alert_payload(experience_level="3-5 Years")
        ).experience_level
        == "MID_LEVEL"
    )

    assert JobAlertUpdateSchema(experience_level="5+").experience_level == "SENIOR"


def test_update_blank_job_title_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpdateSchema(job_title="")

    assert "Job Title is required." in str(exc_info.value)


def test_update_blank_title_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        JobAlertUpdateSchema(title="")

    assert "Job Alert Title is required." in str(exc_info.value)


@pytest.mark.parametrize("preference", ["EMAIL", "IN_APP", "BOTH"])
def test_notification_preference_accepts_supported_values(preference):
    alert = JobAlertUpsertSchema(
        **_valid_job_alert_payload(notification_preference=preference)
    )

    assert alert.notification_preference == preference


@pytest.mark.parametrize(
    ("raw_preference", "stored_preference"),
    [
        (" email ", "EMAIL"),
        ("in-app", "IN_APP"),
        ("in app", "IN_APP"),
        ("InApp", "IN_APP"),
        ("both", "BOTH"),
        ("email and in app", "BOTH"),
    ],
)
def test_notification_preference_normalizes_common_frontend_values(
    raw_preference,
    stored_preference,
):
    alert = JobAlertUpsertSchema(
        **_valid_job_alert_payload(notification_preference=raw_preference)
    )

    assert alert.notification_preference == stored_preference


@pytest.mark.parametrize("preference", ["SMS", "PORTAL_NOTIFICATION"])
def test_notification_preference_rejects_removed_values(preference):
    with pytest.raises(ValidationError):
        JobAlertUpsertSchema(
            **_valid_job_alert_payload(notification_preference=preference)
        )

    with pytest.raises(ValidationError):
        JobAlertUpdateSchema(notification_preference=preference)
