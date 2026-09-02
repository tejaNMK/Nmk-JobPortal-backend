from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssignSubscriptionRequest(BaseModel):

    user_id: UUID

    subscription_id: UUID

    role: str

    auto_renew: bool = False

    remarks: Optional[str] = None

    price_paid: Optional[Decimal] = Field(default=None, ge=Decimal("0"))

    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))

    payment_status: str = "PAID"

    transaction_reference: Optional[str] = None

    invoice_number: Optional[str] = None

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"CANDIDATE", "EMPLOYER", "ADMIN"}:
            raise ValueError("role must be CANDIDATE, EMPLOYER, or ADMIN")
        return normalized

    @field_validator("payment_status")
    @classmethod
    def validate_payment_status(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"FREE", "PAID", "PENDING", "FAILED", "REFUNDED"}:
            raise ValueError("Invalid payment_status")
        return normalized


class SelfSubscribeRequest(BaseModel):
    subscription_id: UUID

    auto_renew: bool = False

    remarks: Optional[str] = None

    payment_status: str = "PAID"

    transaction_reference: Optional[str] = None

    invoice_number: Optional[str] = None

    @field_validator("payment_status")
    @classmethod
    def validate_payment_status(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"FREE", "PAID", "PENDING", "FAILED", "REFUNDED"}:
            raise ValueError("Invalid payment_status")
        return normalized


class RenewSubscriptionRequest(BaseModel):

    subscription_id: Optional[UUID] = None

    remarks: Optional[str] = None


class CancelSubscriptionRequest(BaseModel):

    remarks: Optional[str] = None


class ChangeSubscriptionRequest(BaseModel):

    subscription_id: UUID

    remarks: Optional[str] = None

    reset_usage: bool = True


class SubscriptionActionRequest(BaseModel):

    remarks: Optional[str] = None


class UsageResetRequest(BaseModel):

    feature_name: Optional[str] = None


class UserSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_subscription_id: UUID

    user_id: UUID

    user_email: str = ""

    user_name: str = ""

    subscription_id: UUID

    role: str

    start_date: datetime

    end_date: datetime

    status: str

    payment_status: str

    price_paid: Decimal

    discount_amount: Decimal

    currency: str

    auto_renew: bool

    transaction_reference: Optional[str]

    invoice_number: Optional[str]

    remarks: Optional[str]

    assigned_by: Optional[UUID] = None

    cancelled_at: Optional[datetime] = None

    days_remaining: int = 0

    features: dict[str, Any] = {}


class UserSubscriptionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_subscription_id: UUID

    user_id: UUID

    user_email: str = ""

    subscription_id: UUID

    subscription_name: Optional[str] = None

    subscription_type: Optional[str] = None

    status: str

    billing_cycle: Optional[str] = None

    amount: Decimal

    currency: str

    start_date: datetime

    end_date: datetime

    auto_renew: bool

    cancelled_at: Optional[datetime] = None

    cancellation_reason: Optional[str] = None

    created_at: datetime

    updated_at: datetime


class UserSubscriptionHistoryResponse(BaseModel):

    user_id: UUID

    user_email: str = ""

    subscriptions: list[UserSubscriptionHistoryItem]

    total: int


class UserSubscriptionDetailsUser(BaseModel):
    user_id: UUID
    email: str = ""
    name: str = ""
    role: str = ""


class UserSubscriptionDetailsPlan(BaseModel):
    subscription_id: UUID
    name: str = ""
    description: str = ""
    subscription_type: str = ""
    billing_cycle: str = ""
    price: Decimal
    currency: str = ""


class UserSubscriptionDetailsResponse(BaseModel):
    user_subscription_id: UUID
    user: UserSubscriptionDetailsUser
    subscription: UserSubscriptionDetailsPlan
    status: str
    start_date: datetime
    end_date: datetime
    auto_renew: bool
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CurrentSubscriptionSummary(BaseModel):
    user_subscription_id: UUID
    subscription_id: UUID
    subscription_name: str
    subscription_type: str
    status: str
    billing_cycle: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    auto_renew: bool = False
    is_active: bool


class CurrentSubscriptionPlanResponse(BaseModel):
    subscription_id: UUID
    subscription_name: str = ""
    subscription_type: str = ""
    description: Optional[str] = None
    price: Decimal
    currency: str = ""
    duration_days: int
    billing_cycle: str = ""
    features: dict[str, Any] = {}
    is_featured: bool = False
    is_popular: bool = False
    is_default: bool = False


class CurrentSubscriptionResponse(BaseModel):
    user_subscription_id: UUID
    subscription_id: UUID
    role: str
    status: str
    start_date: datetime
    end_date: datetime
    days_remaining: int = 0
    currency: str
    features: dict[str, Any] = {}
    subscription: CurrentSubscriptionPlanResponse


class SubscriptionUsageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usage_id: UUID
    user_subscription_id: UUID
    user_id: UUID
    feature_name: str
    period_start: datetime
    period_end: datetime
    used_count: int
    created_at: datetime
    updated_at: datetime


class RemainingUsageItem(BaseModel):
    feature_name: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    used_count: int
    limit: Optional[int] = None
    remaining: Optional[int] = None
    unlimited: bool = False


class RemainingUsageResponse(BaseModel):
    user_subscription_id: UUID
    subscription_id: UUID
    usage: list[RemainingUsageItem]
