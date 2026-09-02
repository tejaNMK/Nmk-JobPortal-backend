import pytest
from pydantic import ValidationError

from app.candidate_schema import (
    CandidateExperienceCreateSchema,
    CandidateExperienceUpdateSchema,
)

VALID_EXPERIENCE = {
    "company": "Amoka International",
    "role": "UI/UX Designer",
    "location": "Lahore, Pakistan",
    "key_highlights": "Led the redesign of the checkout flow.",
}

MALICIOUS_PAYLOADS = [
    "<script>alert('test')</script>",
    "<b>Bold Text</b>",
    "<img src=x onerror=alert('XSS')>",
    '<a href="https://example.com">Click Here</a>',
    "javascript:alert(1)",
]


@pytest.mark.parametrize("field", ["company", "role", "location", "key_highlights"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_experience_create_rejects_html_in_each_field(field, payload):
    data = {**VALID_EXPERIENCE, field: payload}
    with pytest.raises(ValidationError) as exc_info:
        CandidateExperienceCreateSchema(**data)
    assert "HTML or script tags are not allowed." in str(exc_info.value)


@pytest.mark.parametrize("field", ["company", "role", "location", "key_highlights"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_experience_update_rejects_html_in_each_field(field, payload):
    with pytest.raises(ValidationError) as exc_info:
        CandidateExperienceUpdateSchema(**{field: payload})
    assert "HTML or script tags are not allowed." in str(exc_info.value)


def test_experience_create_allows_plain_text_with_harmless_symbols():
    data = {
        "company": "Acme & Co.",
        "role": "Software Engineer",
        "location": "Remote",
        "key_highlights": "Improved throughput by 20%, kept latency < 200ms.",
    }
    schema = CandidateExperienceCreateSchema(**data)
    assert schema.company == "Acme & Co."
    assert schema.key_highlights == "Improved throughput by 20%, kept latency < 200ms."


def test_experience_update_allows_partial_plain_text_update():
    schema = CandidateExperienceUpdateSchema(role="Senior Engineer")
    assert schema.role == "Senior Engineer"