from typing import Optional, Generic, TypeVar, List
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import AliasChoices, BaseModel, EmailStr, Field, model_validator
from pydantic import ConfigDict


T = TypeVar("T")


class LoginSchema(BaseModel):
    email: EmailStr
    password: str

    @model_validator(mode="after")
    def validate_email(self):
        if not self.email:
            raise ValueError("Email is required")
        return self


class ForgotPasswordSchema(BaseModel):

    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None

    @model_validator(mode="after")
    def validate_contact(self):

        import re

        if not self.email and not self.mobile_number:
            raise ValueError(
                "Either email or mobile number is required"
            )

        if self.mobile_number:

            phone = self.mobile_number.strip()

            if not re.fullmatch(r"\d{7,15}", phone):
                raise ValueError(
                    "Phone number must be between 7 and 15 digits"
                )

            self.mobile_number = phone

        return self

class ForgotUserIdSchema(BaseModel):

    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None

    @model_validator(mode="after")
    def validate_contact(self):

        import re

        if not self.email and not self.mobile_number:
            raise ValueError(
                "Either email or mobile number is required"
            )

        if self.email:

            email_str = str(self.email)

            if len(email_str) > 50:
                raise ValueError(
                    "Email ID must be at most 50 characters"
                )

        if self.mobile_number:

            phone = self.mobile_number.strip()

            if not re.fullmatch(r"\d{10}", phone):
                raise ValueError(
                    "Phone Number must be exactly 10 digits"
                )

            self.mobile_number = phone

        return self
class ResetPasswordSchema(BaseModel):

    email: Optional[EmailStr] = None
    mobile_number: Optional[str] = None

    otp_code: str
    new_password: str
    confirm_password: str
    

    @model_validator(mode="after")
    def validate_passwords_match(self):
        import re
        if not self.email and not self.mobile_number:
            raise ValueError(
                "Either email or mobile number is required"
            )

        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")

        if not self.otp_code or not str(self.otp_code).strip():
            raise ValueError("OTP code is required")

        otp = str(self.otp_code).strip()
        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP code must be a 6-digit number")

        pwd = str(self.new_password)
        if len(pwd) < 8 or len(pwd) > 25:
            raise ValueError("Password must be between 8 and 25 characters")
        if " " in pwd:
            raise ValueError("Password must not contain spaces")
        if not re.search(r"[A-Z]", pwd):
            raise ValueError("Password must include at least 1 uppercase letter")
        if not re.search(r"[a-z]", pwd):
            raise ValueError("Password must include at least 1 lowercase letter")
        if not re.search(r"\d", pwd):
            raise ValueError("Password must include at least 1 number")
        if not re.search(r"[^A-Za-z0-9]", pwd):
            raise ValueError("Password must include at least 1 special character")

        return self


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str
    sign_out_everywhere: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "sign_out_everywhere",
            "signOutEverywhere",
            "sign_out_all",
            "logout_all_sessions",
        ),
    )

    @model_validator(mode="after")
    def validate_passwords(self):
        import re

        if self.current_password is None or not str(self.current_password).strip():
            raise ValueError("Current Password is required")

        def _validate_complexity(pwd: str, field_label: str):
            if pwd is None or not str(pwd).strip():
                raise ValueError(f"{field_label} is required")

            pwd = str(pwd)
            if len(pwd) < 8 or len(pwd) > 25:
                raise ValueError(f"{field_label} must be between 8 and 25 characters")
            if " " in pwd:
                raise ValueError(f"{field_label} must not contain spaces")
            if not re.search(r"[A-Z]", pwd):
                raise ValueError("Password must include at least 1 uppercase letter")
            if not re.search(r"[a-z]", pwd):
                raise ValueError("Password must include at least 1 lowercase letter")
            if not re.search(r"\d", pwd):
                raise ValueError("Password must include at least 1 number")
            if not re.search(r"[^A-Za-z0-9]", pwd):
                raise ValueError("Password must include at least 1 special character")

        _validate_complexity(self.new_password, "New Password")

        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")

        return self

import re

from app.utils.phone import normalize_phone_number


class SendMobileOtpSchema(BaseModel):
    country_code: str
    phone_number: str

    @model_validator(mode="after")
    def validate_phone(self):

        normalized_phone = normalize_phone_number(self.country_code, self.phone_number)
        self.country_code = normalized_phone.country_code
        self.phone_number = normalized_phone.e164

        return self


class VerifyMobileOtpSchema(BaseModel):
    country_code: str
    phone_number: str
    otp_code: str

    @model_validator(mode="after")
    def validate_otp(self):

        normalized_phone = normalize_phone_number(self.country_code, self.phone_number)
        self.country_code = normalized_phone.country_code
        self.phone_number = normalized_phone.e164
        self.otp_code = self.otp_code.strip()

        if not re.fullmatch(r"\d{6}", self.otp_code):
            raise ValueError(
                "OTP must be exactly 6 digits"
            )

        return self
