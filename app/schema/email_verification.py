from datetime import datetime
from pydantic import BaseModel, EmailStr, model_validator


class SendOtpSchema(BaseModel):
    email: EmailStr

    @model_validator(mode="after")
    def validate_email_len(self):
        email_str = str(self.email)
        if len(email_str) > 50:
            raise ValueError("Email ID must be at most 50 characters")
        return self


class VerifyOtpSchema(BaseModel):
    email: EmailStr
    otp_code: str

    @model_validator(mode="after")
    def validate_otp(self):
        import re

        if self.otp_code is None:
            raise ValueError("OTP code is required")
        otp = str(self.otp_code).strip()
        if not re.fullmatch(r"\d{6}", otp):
            raise ValueError("OTP code must be a 6-digit number")
        self.otp_code = otp
        return self

