import pytest
from pydantic import ValidationError

from app.candidate_schema import (
    CandidateExperienceCreateSchema,
    CandidateExperienceUpdateSchema,
    EXPERIENCE_FIELD_MAX_LENGTHS,
)

VALID_EXPERIENCE = {
    "company": "Amoka International",
    "role": "UI/UX Designer",
    "location": "Lahore, Pakistan",
    "key_highlights": "Led the redesign of the checkout flow.",
}


@pytest.mark.parametrize("field,max_length", EXPERIENCE_FIELD_MAX_LENGTHS.items())
def test_experience_create_rejects_value_over_max_length(field, max_length):
    data = {**VALID_EXPERIENCE, field: "a" * (max_length + 1)}
    with pytest.raises(ValidationError, match="Maximum character limit exceeded."):
        CandidateExperienceCreateSchema(**data)


@pytest.mark.parametrize("field,max_length", EXPERIENCE_FIELD_MAX_LENGTHS.items())
def test_experience_create_allows_value_at_max_length(field, max_length):
    data = {**VALID_EXPERIENCE, field: "a" * max_length}
    schema = CandidateExperienceCreateSchema(**data)
    assert len(getattr(schema, field)) == max_length


@pytest.mark.parametrize("field,max_length", EXPERIENCE_FIELD_MAX_LENGTHS.items())
def test_experience_update_rejects_value_over_max_length(field, max_length):
    with pytest.raises(ValidationError, match="Maximum character limit exceeded."):
        CandidateExperienceUpdateSchema(**{field: "a" * (max_length + 1)})


@pytest.mark.parametrize("field,max_length", EXPERIENCE_FIELD_MAX_LENGTHS.items())
def test_experience_update_allows_value_at_max_length(field, max_length):
    schema = CandidateExperienceUpdateSchema(**{field: "a" * max_length})
    assert len(getattr(schema, field)) == max_length


def test_experience_create_allows_normal_length_values():
    schema = CandidateExperienceCreateSchema(**VALID_EXPERIENCE)
    assert schema.role == "UI/UX Designer"
    assert schema.company == "Amoka International"


def test_experience_schemas_accept_frontend_iso_dates_and_reject_default_dates():
    create_schema = CandidateExperienceCreateSchema(
        **VALID_EXPERIENCE,
        start_date="2020-01-01",
        end_date="2022-06-01",
    )
    update_schema = CandidateExperienceUpdateSchema(start_date="2020-01-01")

    assert create_schema.start_date.isoformat() == "2020-01-01"
    assert create_schema.end_date.isoformat() == "2022-06-01"
    assert update_schema.start_date.isoformat() == "2020-01-01"

    with pytest.raises(ValidationError, match="Please select a valid Start Date"):
        CandidateExperienceCreateSchema(**VALID_EXPERIENCE, start_date="0001-07-01")
    with pytest.raises(ValidationError, match="Please select a valid Start Date"):
        CandidateExperienceUpdateSchema(start_date="0001-07-01")
