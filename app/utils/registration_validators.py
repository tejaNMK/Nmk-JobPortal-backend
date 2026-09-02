"""Thin wrappers around existing registration validation utilities.

The project already provides `app.utils.registration_validation` with the
core rule implementations. This module exists to keep schema files clean and
to provide a stable import path for future refactors.
"""

from app.utils.registration_validation import (  # noqa: F401
    collapse_spaces,
    validate_company_name,
    validate_dropdown_value,
    validate_name,
    validate_optional_website,
    validate_password,
    validate_phone_number,
    normalize_email,
    DESIRED_ROLE_CHOICES,
    TEAM_SIZE_CHOICES,
)

