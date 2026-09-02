from typing import Optional, Generic, TypeVar, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, EmailStr, model_validator, ConfigDict


from app.utils.registration_validators import (
    DESIRED_ROLE_CHOICES,

    TEAM_SIZE_CHOICES,
    normalize_email,
    validate_company_name,
    validate_dropdown_value,
    validate_name,
    validate_optional_website,
    validate_password,
    validate_phone_number,
)



T = TypeVar("T")


class CandidateRegisterSchema(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: str

    email: EmailStr
    phone_number: str
    country_code: str


    password: str
    confirm_password: str

    desired_role: str

    role_code: str = "ROLE_CANDIDATE"

    agree_to_terms: bool

    @model_validator(mode="after")
    def validate_required_fields(self):
        self.first_name = validate_name(
            self.first_name,
            "First name",
            required=True,
            min_length=2,
        )
        self.middle_name = validate_name(
            self.middle_name,
            "Middle name",
            required=False,
            min_length=1,
        )
        self.last_name = validate_name(
            self.last_name,
            "Last name",
            required=True,
            min_length=1,
        )
        self.email = normalize_email(self.email)

        self.desired_role = validate_dropdown_value(
            self.desired_role,
            "Desired role",
            DESIRED_ROLE_CHOICES,
        )

        normalized_phone = validate_phone_number(self.country_code, self.phone_number)
        self.country_code = normalized_phone.country_code
        self.phone_number = normalized_phone.e164

        self.password = validate_password(self.password, "Password")
        self.confirm_password = validate_password(self.confirm_password, "Confirm Password")

        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")

        if not self.agree_to_terms:
            raise ValueError("You must agree to the Terms of Service and Privacy Policy")

        return self


class EmployerRegisterSchema(BaseModel):
    company_name: str

    first_name: str
    middle_name: Optional[str] = None
    last_name: str

    website: Optional[str] = None

    work_email: EmailStr

    phone_number: str
    country_code: str


    password: str

    confirm_password: str

    team_size: Optional[str] = None

    agree_to_terms: bool

    role_code: str = "ROLE_RECRUITER"

    @model_validator(mode="after")
    def validate_required_fields(self):
        self.company_name = validate_company_name(self.company_name)
        self.first_name = validate_name(
            self.first_name,
            "First name",
            required=True,
            min_length=2,
        )

        self.middle_name = validate_name(
            self.middle_name,
            "Middle name",
            required=False,
            min_length=1,
        )
        self.last_name = validate_name(
            self.last_name,
            "Last name",
            required=True,
            min_length=1,
        )

        self.website = validate_optional_website(self.website)
        self.work_email = normalize_email(self.work_email)

        normalized_phone = validate_phone_number(self.country_code, self.phone_number)
        self.country_code = normalized_phone.country_code
        self.phone_number = normalized_phone.e164

        self.team_size = validate_dropdown_value(
            self.team_size,
            "Team size",
            TEAM_SIZE_CHOICES,
        )
        self.password = validate_password(self.password, "Password")
        self.confirm_password = validate_password(self.confirm_password, "Confirm Password")

        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")

        if not self.agree_to_terms:
            raise ValueError("You must accept the Terms and confirm you have hiring authority")

        return self
