import pytest
from pydantic import ValidationError

from app.candidate_schema import (
    CandidateSkillCreateSchema,
    CandidateSkillUpdateSchema,
    CandidateLanguageCreateSchema,
    CandidateLanguageUpdateSchema,
    CandidateEducationCreateSchema,
    CandidateEducationUpdateSchema,
    CertificationEntrySchema,
    CandidateCertificationUpdateSchema,
    CandidateProjectCreateSchema,
    CandidateProjectUpdateSchema,
)

MALICIOUS_PAYLOADS = [
    "<script>alert('test')</script>",
    "<b>Bold Text</b>",
    "<img src=x onerror=alert('XSS')>",
    '<a href="https://example.com">Click Here</a>',
    "javascript:alert(1)",
]


@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_skill_create_rejects_html_in_name(payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateSkillCreateSchema(name=payload, level="EXPERT")


@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_skill_update_rejects_html_in_name(payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateSkillUpdateSchema(name=payload)


def test_skill_create_allows_plain_text():
    schema = CandidateSkillCreateSchema(name="C++ & Python", level="EXPERT")
    assert schema.name == "C++ & Python"


@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_language_create_rejects_html_in_name(payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateLanguageCreateSchema(name=payload, proficiency_level="NATIVE")


@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_language_update_rejects_html_in_name(payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateLanguageUpdateSchema(name=payload)


@pytest.mark.parametrize("field", ["institution", "degree", "field_of_study"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_education_create_rejects_html_in_each_field(field, payload):
    data = {"institution": "University of Lahore", field: payload}
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateEducationCreateSchema(**data)


@pytest.mark.parametrize("field", ["institution", "degree", "field_of_study"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_education_update_rejects_html_in_each_field(field, payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateEducationUpdateSchema(**{field: payload})


def test_education_create_allows_plain_text():
    schema = CandidateEducationCreateSchema(
        institution="University of Lahore",
        degree="BSc Computer Science",
        field_of_study="Software Engineering",
    )
    assert schema.institution == "University of Lahore"


@pytest.mark.parametrize(
    "field", ["name", "issuing_organization", "credential_id", "credential_url"]
)
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_certification_create_rejects_html_in_each_field(field, payload):
    data = {"name": "AWS Certified", "issuing_organization": "Amazon", field: payload}
    if field == "credential_url":
        # credential_url must also look like a URL before the HTML check can
        # even be reached in a realistic payload; simulate script smuggled
        # inside an otherwise well-formed URL.
        data[field] = f"https://example.com/{payload}"
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CertificationEntrySchema(**data)


@pytest.mark.parametrize(
    "field", ["name", "issuing_organization", "credential_id"]
)
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_certification_update_rejects_html_in_each_field(field, payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateCertificationUpdateSchema(**{field: payload})


def test_certification_create_allows_plain_text():
    schema = CertificationEntrySchema(
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services",
        credential_url="https://aws.amazon.com/verify?score=90>80",
    )
    assert schema.name == "AWS Certified Solutions Architect"


@pytest.mark.parametrize("field", ["title", "technologies_used", "description"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_project_create_rejects_html_in_each_field(field, payload):
    data = {"title": "Jobs Portal", field: payload}
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateProjectCreateSchema(**data)


@pytest.mark.parametrize("field", ["title", "technologies_used", "description"])
@pytest.mark.parametrize("payload", MALICIOUS_PAYLOADS)
def test_project_update_rejects_html_in_each_field(field, payload):
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateProjectUpdateSchema(**{field: payload})


def test_project_create_rejects_script_smuggled_in_url():
    with pytest.raises(ValidationError, match="HTML or script tags are not allowed."):
        CandidateProjectCreateSchema(
            title="Jobs Portal",
            project_url="https://example.com/<script>alert(1)</script>",
        )


def test_project_create_allows_plain_text_with_harmless_symbols():
    schema = CandidateProjectCreateSchema(
        title="Jobs Portal",
        technologies_used="React, Node.js, MongoDB",
        project_url="https://example.com",
        description="Reduced load time by 30%, throughput > 500 req/s.",
    )
    assert schema.description == "Reduced load time by 30%, throughput > 500 req/s."