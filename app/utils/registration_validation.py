import re

from app.utils.phone import NormalizedPhoneNumber, normalize_phone_number


NAME_PATTERN = re.compile(r"^[A-Za-z'-]+$")
REPEATED_SPACES = re.compile(r"\s+")

DESIRED_ROLE_CHOICES = {
    "Software Engineer",
    "Product Designer",
    "Project Manager",
    "Data Analyst",
}

TEAM_SIZE_CHOICES = {
    "1-10",
    "11-50",
    "51-200",
    "201-500",
    "501-1000",
    "1000+",
}


def collapse_spaces(value: str) -> str:
    return REPEATED_SPACES.sub(" ", value.strip())


def validate_name(
    value: str | None,
    field_label: str,
    *,
    required: bool = True,
    min_length: int = 1,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field_label} is required")
        return None

    trimmed = str(value).strip()
    if not trimmed:
        if required:
            raise ValueError(f"{field_label} is required")
        return None

    if len(trimmed) < min_length:
        raise ValueError(f"{field_label} must be at least {min_length} characters")
    if len(trimmed) > 30:
        raise ValueError(f"{field_label} must not exceed 30 characters")
    if not NAME_PATTERN.fullmatch(trimmed):
        raise ValueError(
            f"{field_label} must contain only letters, hyphens, and apostrophes"
        )

    return trimmed


def normalize_email(value: str, field_label: str = "Email ID") -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_label} is required")

    email = str(value).strip().lower()
    if len(email) > 50:
        raise ValueError(f"{field_label} must be at most 50 characters")

    return email


def validate_phone_number(
    country_code: str | None,
    phone_number: str | None,
) -> NormalizedPhoneNumber:
    return normalize_phone_number(country_code, phone_number)


def validate_password(value: str | None, field_label: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_label} is required")

    password = str(value)
    if len(password) < 8 or len(password) > 25:
        raise ValueError(f"{field_label} must be between 8 and 25 characters")
    if " " in password:
        raise ValueError(f"{field_label} must not contain spaces")
    if not (
        re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"\d", password)
        and re.search(r"[^A-Za-z0-9]", password)
    ):
        raise ValueError(
            "Password must contain at least one uppercase letter, one lowercase letter, one digit, and one special character"
        )

    return password


def validate_dropdown_value(
    value: str | None,
    field_label: str,
    allowed_values: set[str],
) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_label} is required")

    normalized = collapse_spaces(str(value))
    if normalized not in allowed_values:
        raise ValueError(f"{field_label} is invalid")

    return normalized


def validate_company_name(value: str | None) -> str:
    if value is None or not str(value).strip():
        raise ValueError("Company name is required")

    company_name = collapse_spaces(str(value))
    if len(company_name) < 2:
        raise ValueError("Company name must be at least 2 characters")
    if len(company_name) > 50:
        raise ValueError("Company name must not exceed 50 characters")

    return company_name


def validate_optional_website(value: str | None) -> str | None:
    if value is None:
        return None

    website = str(value).strip()
    if not website:
        raise ValueError("Website must not be blank")
    if len(website) > 100:
        raise ValueError("Website must not exceed 100 characters")

    return website
