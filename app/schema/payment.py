from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class RazorpayCreateOrderRequest(BaseModel):
    subscription_id: UUID
    auto_renew: bool = False


class RazorpayOrderResponse(BaseModel):
    key: str
    order_id: str
    amount: int
    currency: str
    receipt: str
    subscription_id: UUID
    user_subscription_id: UUID
    plan_name: str
    plan_amount: Decimal


class RazorpayVerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RazorpayPaymentVerificationResponse(BaseModel):
    user_subscription_id: UUID
    subscription_id: UUID
    status: str
    payment_status: str
    transaction_reference: Optional[str] = None


class RazorpayPendingPaymentResponse(BaseModel):
    has_pending: bool
    key: Optional[str] = None
    order_id: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    user_subscription_id: Optional[UUID] = None
    subscription_id: Optional[UUID] = None
    plan_name: Optional[str] = None
    plan_amount: Optional[Decimal] = None
    role: Optional[str] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved: bool = False


class RazorpayWebhookResponse(BaseModel):
    processed: bool
    event: Optional[str] = None
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
