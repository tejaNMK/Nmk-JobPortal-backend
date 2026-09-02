from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.utils.timezones import validate_iana_timezone_name


class PasswordPolicySettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    minimum_password_length: Optional[int] = Field(
        default=None,
        alias="min_length",
        ge=6,
        le=128,
    )
    require_uppercase: Optional[bool] = None
    require_lowercase: Optional[bool] = None
    require_number: Optional[bool] = None
    require_special_character: Optional[bool] = None


class EmailNotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    master_email_notifications: Optional[bool] = Field(
        default=None,
        alias="enabled",
    )
    company_approval_updates: Optional[bool] = None
    subscription_updates: Optional[bool] = None
    system_alerts: Optional[bool] = None


class PlatformConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_name: Optional[str] = None
    support_email: Optional[str] = None
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        return validate_iana_timezone_name(value)


class SystemSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    maintenance_mode: bool
    registration_enabled: bool
    candidate_default_subscription_plan: Optional[str] = None
    employer_default_subscription_plan: Optional[str] = None
    password_policy: Dict[str, Any]
    email_notifications: Dict[str, Any]
    platform_config: Dict[str, Any]
    updated_at: datetime
    updated_by: Optional[str] = None
    updated_by_email: Optional[EmailStr] = None
    updated_by_name: Optional[str] = None
    updated_by_role: Optional[str] = None


class SystemSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    maintenance_mode: Optional[bool] = None
    registration_enabled: Optional[bool] = None
    candidate_default_subscription_plan: Optional[str] = None
    employer_default_subscription_plan: Optional[str] = None
    password_policy: Optional[PasswordPolicySettingsUpdate] = None
    email_notifications: Optional[EmailNotificationSettingsUpdate] = None
    platform_config: Optional[PlatformConfigurationUpdate] = None
    minimum_password_length: Optional[int] = Field(
        default=None,
        alias="min_length",
        ge=6,
        le=128,
    )
    require_uppercase: Optional[bool] = None
    require_lowercase: Optional[bool] = None
    require_number: Optional[bool] = None
    require_special_character: Optional[bool] = None
    master_email_notifications: Optional[bool] = None
    company_approval_updates: Optional[bool] = None
    subscription_updates: Optional[bool] = None
    system_alerts: Optional[bool] = None
    platform_name: Optional[str] = None
    support_email: Optional[str] = None
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        return validate_iana_timezone_name(value)
