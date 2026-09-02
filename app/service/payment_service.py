import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from app.config import (
    RAZORPAY_API_BASE_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    commit_rollback,
)
from app.constants.notification_constants import NotificationType
from app.model.subscription.subscription_history import SubscriptionHistory
from app.model.subscription.user_subscription import UserSubscription
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.schema.payment import (
    RazorpayCreateOrderRequest,
    RazorpayOrderResponse,
    RazorpayPendingPaymentResponse,
    RazorpayPaymentVerificationResponse,
)
from app.service.subscription.subscription_bootstrap_service import (
    SubscriptionBootstrapService,
)
from app.service.subscription.user_subscription_service import UserSubscriptionService


logger = logging.getLogger(__name__)


class RazorpayPaymentService:
    SUCCESSFUL_PAYMENT_STATUSES = {"captured"}

    @staticmethod
    def _require_config() -> tuple[str, str]:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise HTTPException(
                status_code=500,
                detail="Razorpay credentials are not configured.",
            )
        return RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

    @staticmethod
    def _amount_to_paise(amount: Decimal) -> int:
        decimal_amount = Decimal(str(amount or 0)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return int(decimal_amount * 100)

    @staticmethod
    def _hmac_sha256(message: bytes, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_checkout_signature(
        *,
        order_id: str,
        payment_id: str,
        signature: str,
        secret: str | None = None,
    ) -> bool:
        _, configured_secret = RazorpayPaymentService._require_config()
        expected = RazorpayPaymentService._hmac_sha256(
            f"{order_id}|{payment_id}".encode("utf-8"),
            secret or configured_secret,
        )
        return hmac.compare_digest(expected, signature or "")

    @staticmethod
    def verify_webhook_signature(
        *,
        body: bytes,
        signature: str,
        secret: str | None = None,
    ) -> bool:
        webhook_secret = secret or RAZORPAY_WEBHOOK_SECRET
        if not webhook_secret:
            raise HTTPException(
                status_code=500,
                detail="Razorpay webhook secret is not configured.",
            )
        expected = RazorpayPaymentService._hmac_sha256(body, webhook_secret)
        return hmac.compare_digest(expected, signature or "")

    @staticmethod
    async def _razorpay_request(
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key_id, key_secret = RazorpayPaymentService._require_config()
        url = f"{RAZORPAY_API_BASE_URL}{path}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(
                    method,
                    url,
                    auth=(key_id, key_secret),
                    json=json,
                )
        except httpx.RequestError as exc:
            logger.exception("Razorpay API request failed.")
            raise HTTPException(
                status_code=502,
                detail="Unable to contact Razorpay.",
            ) from exc

        if response.status_code >= 400:
            logger.warning(
                "Razorpay API returned an error.",
                extra={
                    "status_code": response.status_code,
                    "body": response.text[:500],
                },
            )
            raise HTTPException(
                status_code=502,
                detail="Razorpay rejected the payment request.",
            )
        return response.json()

    @staticmethod
    async def create_subscription_order(
        session,
        *,
        user_id: UUID,
        request: RazorpayCreateOrderRequest,
    ) -> RazorpayOrderResponse:
        key_id, _ = RazorpayPaymentService._require_config()
        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=request.subscription_id,
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        if not plan.is_active:
            raise HTTPException(
                status_code=400,
                detail="Subscription plan is inactive.",
            )

        amount = Decimal(str(plan.price or 0))
        amount_paise = RazorpayPaymentService._amount_to_paise(amount)
        if amount_paise <= 0:
            raise HTTPException(
                status_code=400,
                detail="Free plans do not require Razorpay payment.",
            )

        role = SubscriptionBootstrapService.normalize_subscription_role(
            plan.subscription_type
        )
        UserSubscriptionService._ensure_plan_matches_role(plan, role)
        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=user_id,
            role=role,
        )

        pending_subscription = (
            await UserSubscriptionRepository.get_pending_razorpay_subscription(
                session=session,
                user_id=user_id,
                role=role,
            )
        )
        if pending_subscription:
            try:
                reconciled = await RazorpayPaymentService.reconcile_pending_order(
                    session,
                    pending_subscription,
                )
                if reconciled:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "SUBSCRIPTION_PAYMENT_ALREADY_COMPLETED",
                            "message": (
                                "A pending payment for this subscription was "
                                "completed. Please refresh your subscription status."
                            ),
                            "user_subscription_id": str(
                                pending_subscription.user_subscription_id
                            ),
                            "subscription_id": str(
                                pending_subscription.subscription_id
                            ),
                            "razorpay_order_id": pending_subscription.razorpay_order_id,
                            "status": "ACTIVE",
                            "payment_status": "PAID",
                        },
                    )
            except HTTPException as exc:
                if exc.status_code == 409:
                    raise
                logger.exception(
                    "Unable to reconcile existing pending payment before order creation.",
                    extra={
                        "user_subscription_id": str(
                            pending_subscription.user_subscription_id
                        ),
                        "razorpay_order_id": pending_subscription.razorpay_order_id,
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SUBSCRIPTION_PAYMENT_PENDING",
                    "message": (
                        "A payment is already pending for this user and role. "
                        "Complete or fail the existing payment before choosing "
                        "another subscription plan."
                    ),
                    "user_subscription_id": str(
                        pending_subscription.user_subscription_id
                    ),
                    "subscription_id": str(pending_subscription.subscription_id),
                    "razorpay_order_id": pending_subscription.razorpay_order_id,
                    "same_plan": (
                        pending_subscription.subscription_id == plan.subscription_id
                    ),
                    "status": pending_subscription.status,
                    "payment_status": pending_subscription.payment_status,
                },
            )

        active_subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
            role=role,
        )
        active_plan = None
        if active_subscription:
            active_subscription = await UserSubscriptionService._expire_if_needed(
                session=session,
                user_subscription=active_subscription,
                performed_by=user_id,
            )
        if active_subscription and active_subscription.status == "ACTIVE":
            active_plan = await SubscriptionRepository.get_by_id(
                session=session,
                subscription_id=active_subscription.subscription_id,
            )
            if active_plan and not active_plan.is_default and active_plan.price > 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"User already has an active {role} subscription.",
                )

        receipt = f"sub_{uuid4().hex}"
        order = await RazorpayPaymentService._razorpay_request(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": plan.currency,
                "receipt": receipt,
                "notes": {
                    "user_id": str(user_id),
                    "subscription_id": str(plan.subscription_id),
                },
            },
        )
        order_id = order.get("id")
        if not order_id:
            raise HTTPException(
                status_code=502,
                detail="Razorpay did not return an order id.",
            )

        now = datetime.utcnow()
        pending_subscription = UserSubscription(
            user_id=user_id,
            subscription_id=plan.subscription_id,
            role=role,
            start_date=now,
            end_date=now + timedelta(days=plan.duration_days),
            status="PENDING",
            payment_status="PENDING",
            price_paid=amount,
            discount_amount=Decimal("0.00"),
            currency=plan.currency,
            payment_gateway="RAZORPAY",
            razorpay_order_id=order_id,
            auto_renew=request.auto_renew,
            assigned_by=user_id,
            remarks="Razorpay order created.",
        )
        created = await UserSubscriptionRepository.create(
            session=session,
            user_subscription=pending_subscription,
            commit=False,
        )
        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=created.user_subscription_id,
                subscription_id=created.subscription_id,
                user_id=created.user_id,
                action="PAYMENT_ORDER_CREATED",
                performed_by=user_id,
                new_start_date=created.start_date,
                new_end_date=created.end_date,
                remarks=f"Razorpay order {order_id} created.",
            ),
            commit=False,
        )
        await commit_rollback(session)
        await session.refresh(created)

        return RazorpayOrderResponse(
            key=key_id,
            order_id=order_id,
            amount=amount_paise,
            currency=plan.currency,
            receipt=receipt,
            subscription_id=plan.subscription_id,
            user_subscription_id=created.user_subscription_id,
            plan_name=plan.subscription_name,
            plan_amount=amount,
        )

    @staticmethod
    async def get_pending_subscription_payment(
        session,
        *,
        user_id: UUID,
        role: str,
        sync: bool = False,
    ) -> RazorpayPendingPaymentResponse:
        key_id, _ = RazorpayPaymentService._require_config()
        normalized_role = SubscriptionBootstrapService.normalize_subscription_role(role)
        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=user_id,
            role=normalized_role,
        )

        pending_subscription = (
            await UserSubscriptionRepository.get_pending_razorpay_subscription(
                session=session,
                user_id=user_id,
                role=normalized_role,
            )
        )
        if not pending_subscription:
            return RazorpayPendingPaymentResponse(has_pending=False)

        if sync:
            try:
                reconciled = await RazorpayPaymentService.reconcile_pending_order(
                    session,
                    pending_subscription,
                )
            except HTTPException:
                logger.exception(
                    "Unable to sync pending Razorpay payment lookup.",
                    extra={
                        "user_subscription_id": str(
                            pending_subscription.user_subscription_id
                        ),
                        "razorpay_order_id": pending_subscription.razorpay_order_id,
                    },
                )
                reconciled = False
            if reconciled:
                return RazorpayPendingPaymentResponse(
                    has_pending=False,
                    user_subscription_id=pending_subscription.user_subscription_id,
                    subscription_id=pending_subscription.subscription_id,
                    role=pending_subscription.role,
                    status=pending_subscription.status,
                    payment_status=pending_subscription.payment_status,
                    resolved=True,
                )

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=pending_subscription.subscription_id,
        )
        amount = Decimal(str(pending_subscription.price_paid or 0))
        return RazorpayPendingPaymentResponse(
            has_pending=True,
            key=key_id,
            order_id=pending_subscription.razorpay_order_id,
            amount=RazorpayPaymentService._amount_to_paise(amount),
            currency=pending_subscription.currency,
            user_subscription_id=pending_subscription.user_subscription_id,
            subscription_id=pending_subscription.subscription_id,
            plan_name=getattr(plan, "subscription_name", None),
            plan_amount=amount,
            role=pending_subscription.role,
            status=pending_subscription.status,
            payment_status=pending_subscription.payment_status,
            created_at=pending_subscription.created_at,
        )

    @staticmethod
    async def complete_order_payment(
        session,
        *,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        source: str = "checkout",
        expected_user_id: UUID | None = None,
        provider_order: dict[str, Any] | None = None,
        provider_payment: dict[str, Any] | None = None,
    ) -> RazorpayPaymentVerificationResponse:
        user_subscription = await UserSubscriptionRepository.get_by_razorpay_order_id_for_update(
            session=session,
            razorpay_order_id=razorpay_order_id,
        )
        if not user_subscription:
            raise HTTPException(status_code=404, detail="Payment order not found.")
        if expected_user_id and user_subscription.user_id != expected_user_id:
            raise HTTPException(status_code=404, detail="Payment order not found.")

        if user_subscription.status == "ACTIVE" and user_subscription.payment_status == "PAID":
            if (
                user_subscription.razorpay_payment_id
                and razorpay_payment_id
                and user_subscription.razorpay_payment_id != razorpay_payment_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Payment order was already completed with another payment.",
                )
            return RazorpayPaymentVerificationResponse(
                user_subscription_id=user_subscription.user_subscription_id,
                subscription_id=user_subscription.subscription_id,
                status=user_subscription.status,
                payment_status=user_subscription.payment_status,
                transaction_reference=user_subscription.transaction_reference,
            )

        if user_subscription.status != "PENDING":
            raise HTTPException(
                status_code=400,
                detail="Payment order is not pending.",
            )
        if not razorpay_payment_id:
            raise HTTPException(
                status_code=400,
                detail="Razorpay payment id is required to activate subscription.",
            )

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=user_subscription.subscription_id,
        )
        if not plan or not plan.is_active:
            raise HTTPException(
                status_code=400,
                detail="Active subscription plan required.",
            )
        provider_order = provider_order or await RazorpayPaymentService.fetch_order(
            razorpay_order_id
        )
        provider_payment = provider_payment or await RazorpayPaymentService.fetch_payment(
            razorpay_payment_id
        )
        RazorpayPaymentService._validate_provider_payment(
            user_subscription=user_subscription,
            plan=plan,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            provider_order=provider_order,
            provider_payment=provider_payment,
        )

        now = datetime.utcnow()
        await UserSubscriptionRepository.expire_duplicate_active_subscriptions(
            session=session,
            user_id=user_subscription.user_id,
            role=user_subscription.role,
            keep_user_subscription_id=user_subscription.user_subscription_id,
        )
        user_subscription.start_date = now
        user_subscription.end_date = now + timedelta(days=plan.duration_days)
        user_subscription.status = "ACTIVE"
        user_subscription.payment_status = "PAID"
        user_subscription.transaction_reference = razorpay_payment_id
        user_subscription.razorpay_payment_id = razorpay_payment_id
        user_subscription.payment_verified_at = now
        user_subscription.remarks = f"Razorpay payment verified by {source}."
        updated = await UserSubscriptionRepository.update(
            session=session,
            subscription=user_subscription,
            commit=False,
        )
        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=updated.user_subscription_id,
                subscription_id=updated.subscription_id,
                user_id=updated.user_id,
                action="PAYMENT_VERIFIED",
                performed_by=updated.user_id,
                new_start_date=updated.start_date,
                new_end_date=updated.end_date,
                remarks=f"Razorpay payment verified by {source}.",
            ),
            commit=False,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=updated.user_id,
            action="SUBSCRIPTION_PAYMENT_VERIFIED",
            user_subscription=updated,
            plan=plan,
            description="Subscription payment verified",
            remarks=f"Razorpay payment verified by {source}.",
            metadata={
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "source": source,
            },
        )
        await UserSubscriptionService._notify_subscription_event(
            session,
            user_subscription=updated,
            plan=plan,
            notification_type=NotificationType.PACKAGE_PURCHASED,
            title="Package Purchased",
            message=f"{plan.subscription_name} is now active.",
            event_action=f"payment_verified:{source}",
        )
        await commit_rollback(session)
        await session.refresh(updated)

        return RazorpayPaymentVerificationResponse(
            user_subscription_id=updated.user_subscription_id,
            subscription_id=updated.subscription_id,
            status=updated.status,
            payment_status=updated.payment_status,
            transaction_reference=updated.transaction_reference,
        )

    @staticmethod
    async def verify_checkout_payment(
        session,
        *,
        user_id: UUID,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> RazorpayPaymentVerificationResponse:
        if not RazorpayPaymentService.verify_checkout_signature(
            order_id=razorpay_order_id,
            payment_id=razorpay_payment_id,
            signature=razorpay_signature,
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid Razorpay payment signature.",
            )
        return await RazorpayPaymentService.complete_order_payment(
            session=session,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            source="checkout",
            expected_user_id=user_id,
        )

    @staticmethod
    async def fetch_order(order_id: str) -> dict[str, Any]:
        return await RazorpayPaymentService._razorpay_request(
            "GET",
            f"/orders/{order_id}",
        )

    @staticmethod
    async def fetch_payment(payment_id: str) -> dict[str, Any]:
        return await RazorpayPaymentService._razorpay_request(
            "GET",
            f"/payments/{payment_id}",
        )

    @staticmethod
    async def fetch_order_payments(order_id: str) -> list[dict[str, Any]]:
        response = await RazorpayPaymentService._razorpay_request(
            "GET",
            f"/orders/{order_id}/payments",
        )
        return list(response.get("items") or [])

    @staticmethod
    def _validate_provider_payment(
        *,
        user_subscription,
        plan,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        provider_order: dict[str, Any],
        provider_payment: dict[str, Any],
    ) -> None:
        expected_amount = RazorpayPaymentService._amount_to_paise(
            Decimal(str(user_subscription.price_paid or plan.price or 0))
        )
        expected_currency = str(user_subscription.currency or plan.currency or "").upper()
        payment_order_id = provider_payment.get("order_id")
        payment_id = provider_payment.get("id")
        payment_status = str(provider_payment.get("status") or "").lower()
        payment_amount = provider_payment.get("amount")
        payment_currency = str(provider_payment.get("currency") or "").upper()
        order_id = provider_order.get("id")
        order_amount = provider_order.get("amount")
        order_currency = str(provider_order.get("currency") or "").upper()

        if order_id and order_id != razorpay_order_id:
            raise HTTPException(status_code=400, detail="Razorpay order mismatch.")
        if payment_id and payment_id != razorpay_payment_id:
            raise HTTPException(status_code=400, detail="Razorpay payment mismatch.")
        if payment_order_id != razorpay_order_id:
            raise HTTPException(status_code=400, detail="Razorpay payment order mismatch.")
        if payment_status not in RazorpayPaymentService.SUCCESSFUL_PAYMENT_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="Razorpay payment is not captured.",
            )
        if int(payment_amount or 0) != expected_amount:
            raise HTTPException(status_code=400, detail="Razorpay payment amount mismatch.")
        if payment_currency != expected_currency:
            raise HTTPException(
                status_code=400,
                detail="Razorpay payment currency mismatch.",
            )
        if order_amount is not None and int(order_amount or 0) != expected_amount:
            raise HTTPException(status_code=400, detail="Razorpay order amount mismatch.")
        if order_currency and order_currency != expected_currency:
            raise HTTPException(status_code=400, detail="Razorpay order currency mismatch.")

    @staticmethod
    async def reconcile_pending_order(session, user_subscription) -> bool:
        order_id = user_subscription.razorpay_order_id
        if not order_id:
            return False

        order = await RazorpayPaymentService.fetch_order(order_id)
        if order.get("status") == "paid":
            payment_id = None
            try:
                payments = await RazorpayPaymentService.fetch_order_payments(order_id)
                captured = [
                    item
                    for item in payments
                    if item.get("status") in {"captured", "authorized"}
                ]
                if captured:
                    payment_id = captured[0].get("id")
            except HTTPException:
                logger.exception(
                    "Failed to fetch Razorpay payments during reconciliation.",
                    extra={"razorpay_order_id": order_id},
                )
                return False
            if not payment_id:
                logger.warning(
                    "Skipping paid Razorpay order without a captured payment id.",
                    extra={"razorpay_order_id": order_id},
                )
                return False
            await RazorpayPaymentService.complete_order_payment(
                session=session,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                source="scheduler",
            )
            return True

        if order.get("status") in {"attempted"}:
            return False
        return False

    @staticmethod
    async def mark_order_failed(
        session,
        *,
        razorpay_order_id: str,
        reason: str = "Razorpay payment failed.",
    ) -> bool:
        user_subscription = await UserSubscriptionRepository.get_by_razorpay_order_id(
            session=session,
            razorpay_order_id=razorpay_order_id,
        )
        if not user_subscription or user_subscription.status != "PENDING":
            return False
        user_subscription.status = "PAYMENT_FAILED"
        user_subscription.payment_status = "FAILED"
        user_subscription.remarks = reason
        await UserSubscriptionRepository.update(
            session=session,
            subscription=user_subscription,
            commit=False,
        )
        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=user_subscription.user_subscription_id,
                subscription_id=user_subscription.subscription_id,
                user_id=user_subscription.user_id,
                action="PAYMENT_FAILED",
                performed_by=user_subscription.user_id,
                remarks=reason,
            ),
            commit=False,
        )
        await commit_rollback(session)
        return True
