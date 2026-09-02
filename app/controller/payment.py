import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.schema.common import ResponseSchema, created_response, success_response
from app.schema.payment import (
    RazorpayCreateOrderRequest,
    RazorpayPendingPaymentResponse,
    RazorpayVerifyPaymentRequest,
    RazorpayWebhookResponse,
)
from app.service.payment_service import RazorpayPaymentService


router = APIRouter(prefix="/payments", tags=["Payments"])


def _payload_user_id(payload) -> UUID:
    return UUID(str(payload.get("user_id")))


@router.post(
    "/razorpay/order",
    response_model=ResponseSchema,
    status_code=201,
)
async def create_razorpay_order(
    request: RazorpayCreateOrderRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await RazorpayPaymentService.create_subscription_order(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
    )
    return created_response(
        data=data.model_dump(),
        message="Razorpay order created successfully.",
    )


@router.get(
    "/razorpay/pending",
    response_model=ResponseSchema[RazorpayPendingPaymentResponse],
)
async def get_pending_razorpay_payment(
    role: str = Query(..., min_length=1),
    sync: bool = Query(False),
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await RazorpayPaymentService.get_pending_subscription_payment(
        session=session,
        user_id=_payload_user_id(payload),
        role=role,
        sync=sync,
    )
    return success_response(
        data=data.model_dump(),
        message="Pending Razorpay payment fetched successfully.",
    )


@router.post(
    "/razorpay/verify",
    response_model=ResponseSchema,
)
async def verify_razorpay_payment(
    request: RazorpayVerifyPaymentRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await RazorpayPaymentService.verify_checkout_payment(
        session=session,
        user_id=_payload_user_id(payload),
        razorpay_order_id=request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature,
    )
    return success_response(
        data=data.model_dump(),
        message="Razorpay payment verified successfully.",
    )


@router.post(
    "/razorpay/webhook",
    response_model=ResponseSchema,
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    body = await request.body()
    if not RazorpayPaymentService.verify_webhook_signature(
        body=body,
        signature=x_razorpay_signature or "",
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid Razorpay webhook signature.",
        )
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid Razorpay webhook payload.",
        ) from exc
    event = payload.get("event")
    payment = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    order = (
        payload.get("payload", {})
        .get("order", {})
        .get("entity", {})
    )
    order_id = payment.get("order_id") or order.get("id")
    payment_id = payment.get("id")
    result = None

    if event in {"payment.captured", "order.paid"} and order_id:
        if not payment_id:
            payments = await RazorpayPaymentService.fetch_order_payments(order_id)
            captured = [
                item
                for item in payments
                if item.get("status") in {"captured", "authorized"}
            ]
            if captured:
                payment_id = captured[0].get("id")
        if not payment_id:
            raise HTTPException(
                status_code=409,
                detail="Razorpay payment id is not available yet.",
            )
        verified = await RazorpayPaymentService.complete_order_payment(
            session=session,
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            source="webhook",
            provider_order=order or None,
            provider_payment=payment or None,
        )
        result = verified.model_dump()
    elif event == "payment.failed" and order_id:
        processed = await RazorpayPaymentService.mark_order_failed(
            session=session,
            razorpay_order_id=order_id,
            reason=payment.get("error_description") or "Razorpay payment failed.",
        )
        result = {"failed_marked": processed}

    data = RazorpayWebhookResponse(
        processed=result is not None,
        event=event,
        order_id=order_id,
        payment_id=payment_id,
        result=result,
    )
    return success_response(
        data=data.model_dump(),
        message="Razorpay webhook processed.",
    )
