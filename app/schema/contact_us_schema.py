from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


INQUIRY_TYPE_CHOICES = {
    "JOB_SEEKER_SUPPORT": "JOB_SEEKER_SUPPORT",
    "EMPLOYER_SUPPORT": "EMPLOYER_SUPPORT",
    "TECHNICAL_ISSUE": "TECHNICAL_ISSUE",
    "GENERAL_QUERY": "GENERAL_QUERY",
    "OTHER": "OTHER",
}


def _normalize_choice(value: str, choices: dict[str, str]) -> str:
    if value is None:
        return value

    key = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return choices.get(key, key)


class ContactUsCreateSchema(BaseModel):
    full_name: str = Field(..., examples=["John Doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    phone_number: Optional[str] = Field(
        default=None,
        examples=["9876543210"]
    )

    inquiry_type: str = Field(
        ...,
        examples=["TECHNICAL_ISSUE"]
    )

    custom_subject: Optional[str] = Field(
        default=None,
        examples=["Internship Enquiry"]
    )

    message: str = Field(
        ...,
        examples=["I am unable to apply for jobs."]
    )

    turnstile_token: str = Field(
        ...,
        examples=["0.xxxxxxxxxxxxxxxxxxxxxxxxx"]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "John Doe",
                "email": "john@example.com",
                "phone_number": "9876543210",
                "inquiry_type": "TECHNICAL_ISSUE",
                "custom_subject": None,
                "message": "Unable to apply for jobs.",
                "turnstile_token": "0.xxxxxxxxxxxxxxxxxxxxxxxxx",
            }
        }
    )

    @field_validator("inquiry_type", mode="before")
    @classmethod
    def normalize_inquiry_type(cls, value: str) -> str:
        return _normalize_choice(value, INQUIRY_TYPE_CHOICES)

    @model_validator(mode="after")
    def validate_fields(self):

        self.full_name = self.full_name.strip()

        if len(self.full_name) < 2:
            raise ValueError("Full Name must contain at least 2 characters")

        if len(self.full_name) > 100:
            raise ValueError("Full Name cannot exceed 100 characters")

        if not re.match(r"^[A-Za-z\s.'-]+$", self.full_name):
            raise ValueError("Full Name contains invalid characters")

        if self.phone_number:

            self.phone_number = self.phone_number.strip()

            if not self.phone_number.isdigit():
                raise ValueError("Phone Number must contain digits only")

            if len(self.phone_number) < 10 or len(self.phone_number) > 15:
                raise ValueError("Phone Number must contain between 10 and 15 digits")

        allowed = set(INQUIRY_TYPE_CHOICES.values())

        if self.inquiry_type not in allowed:
            raise ValueError("Invalid Inquiry Type")

        if self.inquiry_type == "OTHER":

            if not self.custom_subject:
                raise ValueError(
                    "Custom Subject is required when Inquiry Type is OTHER"
                )

            self.custom_subject = self.custom_subject.strip()

            if len(self.custom_subject) < 3:
                raise ValueError(
                    "Custom Subject must contain at least 3 characters"
                )

            if len(self.custom_subject) > 150:
                raise ValueError(
                    "Custom Subject cannot exceed 150 characters"
                )

        self.message = self.message.strip()

        if len(self.message) < 10:
            raise ValueError(
                "Message must contain at least 10 characters"
            )

        if len(self.message) > 5000:
            raise ValueError(
                "Message cannot exceed 5000 characters"
            )

        if not self.turnstile_token.strip():
            raise ValueError(
                "Captcha validation token is required"
            )

        return self


class ContactUsResponseSchema(BaseModel):
    inquiry_id: str
    email_status: str

    model_config = ConfigDict(from_attributes=True)