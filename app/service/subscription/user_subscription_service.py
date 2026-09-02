import logging
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from app.utils.utc import utc_now_naive

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.subscription.subscription_history import SubscriptionHistory
from app.model.subscription.user_subscription import UserSubscription
from app.repository.authentication.users import UsersRepository
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.repository.subscription.user_subscription_repo import (
    UserSubscriptionRepository,
)
from app.schema.subscription.user_subscription import (
    AssignSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeSubscriptionRequest,
    CurrentSubscriptionSummary,
    RenewSubscriptionRequest,
    CurrentSubscriptionPlanResponse,
    CurrentSubscriptionResponse,
    RemainingUsageItem,
    RemainingUsageResponse,
    SubscriptionActionRequest,
    SubscriptionUsageItem,
    SelfSubscribeRequest,
    UsageResetRequest,
    UserSubscriptionHistoryItem,
    UserSubscriptionHistoryResponse,
    UserSubscriptionDetailsPlan,
    UserSubscriptionDetailsResponse,
    UserSubscriptionDetailsUser,
    UserSubscriptionResponse,
)
from app.constants.notification_constants import NotificationType, ReferenceType
from app.service.notification_service import NotificationService
from app.service.subscription.subscription_bootstrap_service import (
    ROLE_CODES_BY_SUBSCRIPTION_ROLE,
    SubscriptionBootstrapService,
)
from app.service.super_admin.activity_log_service import ActivityLogService


def _current_week_window() -> tuple[datetime, datetime]:
    now = utc_now_naive()
    week_start = datetime(now.year, now.month, now.day) - timedelta(
        days=now.weekday()
    )
    return week_start, week_start + timedelta(days=7)


VALID_ROLES = {"CANDIDATE", "EMPLOYER", "ADMIN"}
VALID_STATUSES = {
    "ACTIVE",
    "CANCELLED",
    "EXPIRED",
    "PENDING",
    "SUSPENDED",
    "PAYMENT_FAILED",
    "REFUNDED",
}
FINAL_STATUSES = {"CANCELLED", "REFUNDED"}
MUTABLE_STATUSES = {"ACTIVE", "SUSPENDED", "EXPIRED", "PENDING", "PAYMENT_FAILED"}
VALID_STATUS_TRANSITIONS = {
    "ACTIVE": {"SUSPENDED", "CANCELLED", "EXPIRED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED", "EXPIRED"},
    "EXPIRED": {"ACTIVE"},
    "PENDING": {"ACTIVE", "CANCELLED", "PAYMENT_FAILED"},
    "PAYMENT_FAILED": {"ACTIVE", "CANCELLED"},
    "CANCELLED": set(),
    "REFUNDED": set(),
}
logger = logging.getLogger(__name__)


def _utc_now_naive() -> datetime:
    return utc_now_naive()


def _days_remaining(end_date: datetime, now: datetime | None = None) -> int:
    now = now or _utc_now_naive()
    return max((end_date - now).days, 0)


def _normalize_feature_key(key: str) -> str:
    normalized = []
    previous = ""
    for char in str(key or "").strip():
        if char.isupper() and previous and (previous.islower() or previous.isdigit()):
            normalized.append("_")
        if char.isalnum():
            normalized.append(char.lower())
        else:
            normalized.append("_")
        previous = char
    return "_".join("".join(normalized).split("_"))


def _subscription_features(subscription) -> dict:
    raw_features = dict(getattr(subscription, "feature_flags", None) or {})
    features = dict(raw_features)
    for key, value in raw_features.items():
        normalized_key = _normalize_feature_key(key)
        if normalized_key and normalized_key not in features:
            features[normalized_key] = value
    legacy = {
        "max_published_jobs": getattr(subscription, "max_published_jobs", None),
        "max_job_alerts": subscription.max_job_alerts,
        "max_resume_uploads": subscription.max_resume_uploads,
    }
    for key, value in legacy.items():
        if value is not None and key not in features:
            features[key] = value
    return features


def _response(user_subscription, subscription=None, user=None) -> UserSubscriptionResponse:
    return UserSubscriptionResponse(
        user_subscription_id=user_subscription.user_subscription_id,
        user_id=user_subscription.user_id,
        user_email=getattr(user, "email", None) or "",
        user_name=_user_display_name(user),
        subscription_id=user_subscription.subscription_id,
        role=user_subscription.role,
        start_date=user_subscription.start_date,
        end_date=user_subscription.end_date,
        status=user_subscription.status,
        payment_status=user_subscription.payment_status,
        price_paid=user_subscription.price_paid,
        discount_amount=user_subscription.discount_amount,
        currency=user_subscription.currency,
        auto_renew=user_subscription.auto_renew,
        transaction_reference=user_subscription.transaction_reference,
        invoice_number=user_subscription.invoice_number,
        remarks=user_subscription.remarks,
        assigned_by=user_subscription.assigned_by,
        cancelled_at=user_subscription.cancelled_at,
        days_remaining=_days_remaining(user_subscription.end_date),
        features=_subscription_features(subscription) if subscription else {},
    )


def _cancellation_reason(user_subscription) -> str | None:
    if getattr(user_subscription, "cancelled_at", None) or (
        getattr(user_subscription, "status", "") or ""
    ).upper() == "CANCELLED":
        return getattr(user_subscription, "remarks", None)
    return None


def _history_response(
    user_subscription,
    subscription=None,
    user_email: str = "",
) -> UserSubscriptionHistoryItem:
    return UserSubscriptionHistoryItem(
        user_subscription_id=user_subscription.user_subscription_id,
        user_id=user_subscription.user_id,
        user_email=user_email,
        subscription_id=user_subscription.subscription_id,
        subscription_name=getattr(subscription, "subscription_name", None),
        subscription_type=getattr(subscription, "subscription_type", None),
        status=user_subscription.status,
        billing_cycle=getattr(subscription, "billing_cycle", None),
        amount=user_subscription.price_paid,
        currency=user_subscription.currency,
        start_date=user_subscription.start_date,
        end_date=user_subscription.end_date,
        auto_renew=user_subscription.auto_renew,
        cancelled_at=user_subscription.cancelled_at,
        cancellation_reason=_cancellation_reason(user_subscription),
        created_at=user_subscription.created_at,
        updated_at=user_subscription.updated_at,
    )


def _user_display_name(user) -> str:
    if not user:
        return ""
    return " ".join(
        part
        for part in (
            getattr(user, "first_name", None),
            getattr(user, "middle_name", None),
            getattr(user, "last_name", None),
        )
        if part
    )


def _details_response(user_subscription, user=None, subscription=None):
    return UserSubscriptionDetailsResponse(
        user_subscription_id=user_subscription.user_subscription_id,
        user=UserSubscriptionDetailsUser(
            user_id=user_subscription.user_id,
            name=_user_display_name(user),
            email=getattr(user, "email", None) or "",
            role=user_subscription.role or "",
        ),
        subscription=UserSubscriptionDetailsPlan(
            subscription_id=user_subscription.subscription_id,
            name=getattr(subscription, "subscription_name", None) or "",
            description=getattr(subscription, "description", None) or "",
            subscription_type=getattr(subscription, "subscription_type", None) or "",
            billing_cycle=getattr(subscription, "billing_cycle", None) or "",
            price=getattr(subscription, "price", None) or Decimal("0"),
            currency=getattr(subscription, "currency", None) or "",
        ),
        status=user_subscription.status,
        start_date=user_subscription.start_date,
        end_date=user_subscription.end_date,
        auto_renew=user_subscription.auto_renew,
        cancelled_at=user_subscription.cancelled_at,
        cancellation_reason=_cancellation_reason(user_subscription),
        created_at=user_subscription.created_at,
        updated_at=user_subscription.updated_at,
    )


def _current_subscription_response(user_subscription, subscription):
    features = _subscription_features(subscription) if subscription else {}
    return CurrentSubscriptionResponse(
        user_subscription_id=user_subscription.user_subscription_id,
        subscription_id=user_subscription.subscription_id,
        role=user_subscription.role,
        status=user_subscription.status,
        start_date=user_subscription.start_date,
        end_date=user_subscription.end_date,
        days_remaining=_days_remaining(user_subscription.end_date),
        currency=user_subscription.currency,
        features=features,
        subscription=CurrentSubscriptionPlanResponse(
            subscription_id=user_subscription.subscription_id,
            subscription_name=getattr(subscription, "subscription_name", None) or "",
            subscription_type=getattr(subscription, "subscription_type", None) or "",
            description=getattr(subscription, "description", None),
            price=getattr(subscription, "price", None) or Decimal("0"),
            currency=getattr(subscription, "currency", None) or user_subscription.currency,
            duration_days=getattr(subscription, "duration_days", None) or 0,
            billing_cycle=getattr(subscription, "billing_cycle", None) or "",
            features=features,
            is_featured=bool(getattr(subscription, "is_featured", False)),
            is_popular=bool(getattr(subscription, "is_popular", False)),
            is_default=bool(getattr(subscription, "is_default", False)),
        ),
    )


def _subscription_summary(user_subscription, subscription) -> CurrentSubscriptionSummary:
    return CurrentSubscriptionSummary(
        user_subscription_id=user_subscription.user_subscription_id,
        subscription_id=user_subscription.subscription_id,
        subscription_name=getattr(subscription, "subscription_name", None) or "",
        subscription_type=(
            getattr(subscription, "subscription_type", None)
            or getattr(user_subscription, "role", None)
            or ""
        ),
        status=user_subscription.status,
        billing_cycle=getattr(subscription, "billing_cycle", None),
        start_date=user_subscription.start_date,
        end_date=user_subscription.end_date,
        auto_renew=bool(getattr(user_subscription, "auto_renew", False)),
        is_active=True,
    )


def _is_current_subscription_assignment(
    user_subscription,
    subscription,
    expected_type: str | None = None,
) -> bool:
    if not user_subscription or not subscription:
        return False
    now = _utc_now_naive()
    plan_type = (getattr(subscription, "subscription_type", "") or "").upper()
    assignment_role = (getattr(user_subscription, "role", "") or "").upper()
    if expected_type and (
        plan_type != expected_type.upper()
        or assignment_role != expected_type.upper()
    ):
        return False
    return (
        (getattr(user_subscription, "status", "") or "").upper() == "ACTIVE"
        and (
            getattr(user_subscription, "start_date", None) is None
            or user_subscription.start_date <= now
        )
        and (
            getattr(user_subscription, "end_date", None) is None
            or user_subscription.end_date > now
        )
        and bool(getattr(subscription, "is_active", False))
    )


class UserSubscriptionService:
    @staticmethod
    async def _repo_create(session, user_subscription):
        try:
            return await UserSubscriptionRepository.create(
                session=session,
                user_subscription=user_subscription,
                commit=False,
            )
        except TypeError:
            return await UserSubscriptionRepository.create(
                session=session,
                user_subscription=user_subscription,
            )

    @staticmethod
    async def _repo_update(session, user_subscription):
        try:
            return await UserSubscriptionRepository.update(
                session=session,
                subscription=user_subscription,
                commit=False,
            )
        except TypeError:
            return await UserSubscriptionRepository.update(
                session=session,
                subscription=user_subscription,
            )

    @staticmethod
    async def _repo_cancel(session, user_subscription):
        try:
            return await UserSubscriptionRepository.cancel_subscription(
                session=session,
                user_subscription=user_subscription,
                commit=False,
            )
        except TypeError:
            return await UserSubscriptionRepository.cancel_subscription(
                session=session,
                user_subscription=user_subscription,
            )

    @staticmethod
    async def _log_user_subscription_activity(
        session,
        *,
        performed_by: UUID | None,
        action: str,
        user_subscription,
        plan=None,
        description: str,
        remarks: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        actor_role = "SUPER_ADMIN" if performed_by else None
        plan_name = getattr(plan, "subscription_name", None)
        metadata_payload = {
            "user_id": str(user_subscription.user_id),
            "subscription_id": str(user_subscription.subscription_id),
            "status": user_subscription.status,
            "role": user_subscription.role,
        }
        if remarks:
            metadata_payload["remarks"] = remarks
        if metadata:
            metadata_payload.update(metadata)

        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=performed_by,
            actor_role=actor_role,
            action=action,
            entity_type="USER_SUBSCRIPTION",
            entity_id=str(user_subscription.user_subscription_id),
            target_entity_name=plan_name,
            description=description,
            metadata=metadata_payload,
            commit=False,
        )

    @staticmethod
    async def _notify_subscription_event(
        session,
        *,
        user_subscription,
        plan=None,
        notification_type: str,
        title: str,
        message: str,
        event_action: str,
        commit: bool = False,
    ) -> None:
        await NotificationService.create_notification(
            session=session,
            recipient_id=str(user_subscription.user_id),
            recipient_role=f"ROLE_{user_subscription.role}",
            title=title,
            message=message,
            notification_type=notification_type,
            reference_type=ReferenceType.SUBSCRIPTION,
            reference_id=str(user_subscription.user_subscription_id),
            entity_type=ReferenceType.SUBSCRIPTION,
            entity_id=str(user_subscription.user_subscription_id),
            target_route="/subscription/current",
            metadata={
                "package_id": str(user_subscription.subscription_id),
                "subscription_id": str(user_subscription.subscription_id),
                "user_subscription_id": str(
                    user_subscription.user_subscription_id
                ),
                "subscription_name": getattr(
                    plan,
                    "subscription_name",
                    None,
                ),
                "role": user_subscription.role,
                "status": user_subscription.status,
                "end_date": (
                    user_subscription.end_date.isoformat()
                    if user_subscription.end_date
                    else None
                ),
            },
            event_key=(
                f"subscription:{event_action}:"
                f"{user_subscription.user_subscription_id}"
            ),
            commit=commit,
        )

    @staticmethod
    async def _ensure_user_and_role(session, user_id: UUID, role: str):
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        user = await UsersRepository.find_by_user_id(
            session=session,
            user_id=str(user_id),
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        role_codes = {item.role_code for item in user.roles}
        expected_roles = ROLE_CODES_BY_SUBSCRIPTION_ROLE.get(
            role,
            {f"ROLE_{role}"},
        )
        if role_codes.isdisjoint(expected_roles):
            raise HTTPException(
                status_code=400,
                detail=f"User does not have {role} role.",
            )
        return user

    @staticmethod
    def _role_from_user(user) -> str | None:
        role_codes = {
            (getattr(role, "role_code", "") or "").upper()
            for role in getattr(user, "roles", []) or []
        }
        for role, codes in (
            ("EMPLOYER", {"ROLE_EMPLOYER", "ROLE_RECRUITER"}),
            ("CANDIDATE", {"ROLE_CANDIDATE"}),
            ("ADMIN", {"ROLE_ADMIN", "ROLE_SUPER_ADMIN"}),
        ):
            if not role_codes.isdisjoint(codes):
                return role
        return None

    @staticmethod
    async def _infer_expected_subscription_type(
        session,
        user_id: UUID,
        expected_type: str | None = None,
    ) -> str | None:
        if expected_type:
            return SubscriptionBootstrapService.normalize_subscription_role(
                expected_type
            )
        user = await UsersRepository.find_by_user_id(
            session=session,
            user_id=str(user_id),
        )
        return UserSubscriptionService._role_from_user(user)

    @staticmethod
    async def _current_subscription_pair(
        session,
        user_id: UUID,
        expected_type: str | None = None,
        *,
        assign_default: bool = True,
    ):
        expected_type = await UserSubscriptionService._infer_expected_subscription_type(
            session=session,
            user_id=user_id,
            expected_type=expected_type,
        )

        rows = await UserSubscriptionRepository.list_current_subscription_candidates(
            session=session,
            user_id=user_id,
            expected_type=expected_type,
            limit=2,
        )
        if len(rows) > 1:
            logger.warning(
                "Duplicate active subscriptions detected for user_id=%s type=%s",
                user_id,
                expected_type or "ANY",
            )
        if rows:
            return rows[0]

        if not assign_default or not expected_type:
            return None

        try:
            assigned = await SubscriptionBootstrapService.ensure_user_subscription(
                session=session,
                user_id=user_id,
                role=expected_type,
                remarks="Assigned default subscription for current session lookup.",
            )
        except HTTPException:
            return None

        rows = await UserSubscriptionRepository.list_current_subscription_candidates(
            session=session,
            user_id=user_id,
            expected_type=expected_type,
            limit=2,
        )
        if rows:
            return rows[0]

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=assigned.subscription_id,
        )
        if (
            _is_current_subscription_assignment(
                assigned,
                plan,
                expected_type=expected_type,
            )
        ):
            return assigned, plan
        return None

    @staticmethod
    async def get_current_subscription_summary(
        session: AsyncSession,
        user_id: UUID,
        expected_type: str | None = None,
    ) -> CurrentSubscriptionSummary | None:
        pair = await UserSubscriptionService._current_subscription_pair(
            session=session,
            user_id=user_id,
            expected_type=expected_type,
            assign_default=True,
        )
        if not pair:
            return None
        user_subscription, subscription = pair
        return _subscription_summary(user_subscription, subscription)

    @staticmethod
    def _ensure_plan_matches_role(subscription, role: str) -> str:
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        plan_role = SubscriptionBootstrapService.normalize_subscription_role(
            getattr(subscription, "subscription_type", "")
        )
        if plan_role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail="Invalid subscription plan type.",
            )
        if plan_role != role:
            raise HTTPException(
                status_code=400,
                detail=f"{plan_role} plans cannot be assigned to {role} users.",
            )
        return plan_role

    @staticmethod
    async def _expire_if_needed(
        session,
        user_subscription,
        performed_by: UUID | None = None,
        *,
        assign_default: bool = False,
    ):
        if (
            user_subscription
            and user_subscription.status == "ACTIVE"
            and _utc_now_naive() > user_subscription.end_date
        ):
            old_start = user_subscription.start_date
            old_end = user_subscription.end_date
            user_subscription.status = "EXPIRED"
            session.add(user_subscription)
            session.add(
                SubscriptionHistory(
                    user_subscription_id=user_subscription.user_subscription_id,
                    subscription_id=user_subscription.subscription_id,
                    user_id=user_subscription.user_id,
                    action="EXPIRED",
                    performed_by=performed_by,
                    old_start_date=old_start,
                    old_end_date=old_end,
                    new_start_date=user_subscription.start_date,
                    new_end_date=user_subscription.end_date,
                    remarks="Subscription expired automatically during validation.",
                )
            )
            await UserSubscriptionService._notify_subscription_event(
                session,
                user_subscription=user_subscription,
                notification_type=NotificationType.SUBSCRIPTION_EXPIRING,
                title="Subscription Expired",
                message="Your subscription has expired.",
                event_action="expired",
            )
            await session.commit()
            await session.refresh(user_subscription)
            if assign_default:
                return await SubscriptionBootstrapService.ensure_user_subscription(
                    session=session,
                    user_id=user_subscription.user_id,
                    role=user_subscription.role,
                    assigned_by=performed_by,
                    remarks="Assigned default subscription after expiration.",
                )
        return user_subscription

    @staticmethod
    async def _record_history(
        session,
        user_subscription,
        *,
        action: str,
        performed_by: UUID | None = None,
        old_start_date: datetime | None = None,
        old_end_date: datetime | None = None,
        remarks: str | None = None,
        commit: bool = True,
    ):
        return await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=user_subscription.user_subscription_id,
                subscription_id=user_subscription.subscription_id,
                user_id=user_subscription.user_id,
                action=action,
                performed_by=performed_by,
                old_start_date=old_start_date,
                old_end_date=old_end_date,
                new_start_date=user_subscription.start_date,
                new_end_date=user_subscription.end_date,
                remarks=remarks,
            ),
            commit=commit,
        )

    # ==========================================
    # ASSIGN SUBSCRIPTION
    # ==========================================

    @staticmethod
    async def assign_subscription(
        session,
        request: AssignSubscriptionRequest,
        assigned_by: UUID | None = None,
    ):
        role = SubscriptionBootstrapService.normalize_subscription_role(
            request.role
        )
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid user role.")

        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=request.user_id,
            role=role,
        )

        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=request.subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        if not subscription.is_active:
            raise HTTPException(
                status_code=400,
                detail="Subscription plan is inactive.",
            )
        UserSubscriptionService._ensure_plan_matches_role(subscription, role)

        active_subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=request.user_id,
            role=role,
        )
        active_subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=active_subscription,
            performed_by=assigned_by,
        )
        if active_subscription and active_subscription.status == "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail=f"User already has an active {role} subscription.",
            )

        start_date = _utc_now_naive()

        end_date = start_date + timedelta(
            days=subscription.duration_days,
        )

        user_subscription = UserSubscription(
            user_id=request.user_id,
            subscription_id=request.subscription_id,
            role=role,
            start_date=start_date,
            end_date=end_date,
            status="ACTIVE",
            payment_status=request.payment_status,

            price_paid=(
                request.price_paid
                if request.price_paid is not None
                else subscription.price
            ),
            discount_amount=request.discount_amount,
            currency=subscription.currency,
            transaction_reference=request.transaction_reference,
            invoice_number=request.invoice_number,
            auto_renew=request.auto_renew,
            assigned_by=assigned_by,
            remarks=request.remarks,
        )

        created = await UserSubscriptionService._repo_create(session, user_subscription)

        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=created.user_subscription_id,
                subscription_id=created.subscription_id,
                user_id=created.user_id,
                action="ASSIGNED",
                performed_by=assigned_by,
                new_start_date=created.start_date,
                new_end_date=created.end_date,
                remarks=request.remarks,
            ),
            commit=False,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=assigned_by,
            action="SUBSCRIPTION_ASSIGNED",
            user_subscription=created,
            plan=subscription,
            description="Subscription assigned to user",
            remarks=request.remarks,
            metadata={
                "payment_status": created.payment_status,
                "auto_renew": created.auto_renew,
            },
        )
        await UserSubscriptionService._notify_subscription_event(
            session,
            user_subscription=created,
            plan=subscription,
            notification_type=NotificationType.PACKAGE_PURCHASED,
            title="Package Purchased",
            message=(
                f"{getattr(subscription, 'subscription_name', 'Subscription')} "
                "is now active."
            ),
            event_action="assigned",
        )
        await commit_rollback(session)
        return _response(created, subscription)

    @staticmethod
    async def assign_default_subscription(
        session,
        *,
        user_id: UUID,
        role: str,
        assigned_by: UUID | None = None,
        remarks: str | None = None,
        commit: bool = True,
    ):
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid user role.")

        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=user_id,
            role=role,
        )
        assigned = await SubscriptionBootstrapService.ensure_user_subscription(
            session=session,
            user_id=user_id,
            role=role,
            assigned_by=assigned_by,
            remarks=remarks,
            commit=commit,
        )
        if assigned_by:
            plan = await SubscriptionRepository.get_by_id(
                session=session,
                subscription_id=assigned.subscription_id,
            )
            await UserSubscriptionService._log_user_subscription_activity(
                session,
                performed_by=assigned_by,
                action="SUBSCRIPTION_ASSIGNED",
                user_subscription=assigned,
                plan=plan,
                description="Default subscription assigned to user",
                remarks=remarks,
                metadata={"default_assignment": True},
            )
        return assigned

    @staticmethod
    async def subscribe_self(
        session,
        user_id: UUID,
        request: SelfSubscribeRequest,
    ):
        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=request.subscription_id,
        )
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription.is_active:
            raise HTTPException(status_code=400, detail="Subscription plan is inactive.")

        role = SubscriptionBootstrapService.normalize_subscription_role(
            subscription.subscription_type
        )
        UserSubscriptionService._ensure_plan_matches_role(subscription, role)
        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=user_id,
            role=role,
        )
        if Decimal(str(subscription.price or 0)) > 0:
            raise HTTPException(
                status_code=400,
                detail="Paid plans must be purchased through Razorpay checkout.",
            )

        active_subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
            role=role,
        )
        active_subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=active_subscription,
            performed_by=user_id,
        )
        if active_subscription and active_subscription.status == "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail=f"User already has an active {role} subscription.",
            )

        start_date = _utc_now_naive()
        user_subscription = UserSubscription(
            user_id=user_id,
            subscription_id=request.subscription_id,
            role=role,
            start_date=start_date,
            end_date=start_date + timedelta(days=subscription.duration_days),
            status="ACTIVE",
            payment_status="FREE",
            price_paid=subscription.price,
            discount_amount=Decimal("0.00"),
            currency=subscription.currency,
            transaction_reference=request.transaction_reference,
            invoice_number=request.invoice_number,
            auto_renew=request.auto_renew,
            assigned_by=user_id,
            remarks=request.remarks,
        )

        created = await UserSubscriptionService._repo_create(session, user_subscription)
        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=created.user_subscription_id,
                subscription_id=created.subscription_id,
                user_id=created.user_id,
                action="SELF_SUBSCRIBED",
                performed_by=user_id,
                new_start_date=created.start_date,
                new_end_date=created.end_date,
                remarks=request.remarks,
            ),
            commit=False,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=user_id,
            action="SUBSCRIPTION_SELF_SUBSCRIBED",
            user_subscription=created,
            plan=subscription,
            description="User subscribed to plan",
            remarks=request.remarks,
            metadata={
                "payment_status": created.payment_status,
                "auto_renew": created.auto_renew,
            },
        )
        await UserSubscriptionService._notify_subscription_event(
            session,
            user_subscription=created,
            plan=subscription,
            notification_type=NotificationType.PACKAGE_PURCHASED,
            title="Package Purchased",
            message=(
                f"{getattr(subscription, 'subscription_name', 'Subscription')} "
                "is now active."
            ),
            event_action="self_subscribed",
        )
        await commit_rollback(session)
        return _response(created, subscription)

    # ==========================================
    # ACTIVE SUBSCRIPTION
    # ==========================================

    @staticmethod
    async def get_active_subscription(
        session,
        user_id: UUID,
    ):

        subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
        )
        subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=subscription,
            assign_default=True,
        )

        if not subscription or subscription.status != "ACTIVE":
            raise HTTPException(
                status_code=404,
                detail="No active subscription found.",
            )

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription.subscription_id,
        )
        return _response(subscription, plan)

    @staticmethod
    async def get_current_subscription(session, user_id: UUID):
        pair = await UserSubscriptionService._current_subscription_pair(
            session=session,
            user_id=user_id,
            assign_default=True,
        )

        if not pair:
            raise HTTPException(status_code=404, detail="No subscription found.")

        user_subscription, plan = pair
        return _current_subscription_response(user_subscription, plan)

    # ==========================================
    # HISTORY
    # ==========================================

    @staticmethod
    async def get_history(
        session,
        user_id: UUID,
    ):

        logger.info("Fetching subscription history for user_id=%s", user_id)
        try:
            user_identity = await UserSubscriptionRepository.get_active_user_identity(
                session=session,
                user_id=user_id,
            )
            if not user_identity:
                raise HTTPException(status_code=404, detail="User not found.")

            history = await UserSubscriptionRepository.get_history(
                session=session,
                user_id=user_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to fetch subscription history for user_id=%s",
                user_id,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch subscription history.",
            ) from exc

        return UserSubscriptionHistoryResponse(
            user_id=user_id,
            user_email=user_identity.email or "",
            subscriptions=[
                _history_response(
                    user_subscription,
                    subscription,
                    user_email=user_identity.email or "",
                )
                for user_subscription, subscription in history
            ],
            total=len(history),
        )

    # ==========================================
    # RENEW SUBSCRIPTION
    # ==========================================

    @staticmethod
    async def renew_subscription(
        session,
        user_id: UUID,
        request: RenewSubscriptionRequest,
        performed_by: UUID | None = None,
        user_subscription_id: UUID | None = None,
    ):

        user_subscription = None
        if user_subscription_id:
            user_subscription = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if user_subscription and user_subscription.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not user_subscription:
            user_subscription = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )
        if not user_subscription:
            user_subscription = await UserSubscriptionRepository.get_latest_subscription(
                session=session,
                user_id=user_id,
            )

        if not user_subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        user_subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=user_subscription,
            performed_by=performed_by,
        )

        if user_subscription.status in FINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Cancelled subscriptions cannot be renewed.",
            )
        if user_subscription.status == "SUSPENDED":
            raise HTTPException(
                status_code=400,
                detail="Suspended subscriptions must be resumed before renewal.",
            )

        plan_id = request.subscription_id or user_subscription.subscription_id
        subscription_plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=plan_id,
        )
        if not subscription_plan:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription_plan.is_active:
            raise HTTPException(status_code=400, detail="Subscription plan is inactive.")
        UserSubscriptionService._ensure_plan_matches_role(
            subscription_plan,
            user_subscription.role,
        )

        old_start = user_subscription.start_date
        old_end = user_subscription.end_date
        start_from = (
            user_subscription.end_date
            if user_subscription.status == "ACTIVE"
            else _utc_now_naive()
        )
        if request.subscription_id:
            user_subscription.subscription_id = request.subscription_id

        user_subscription.start_date = (
            user_subscription.start_date
            if user_subscription.status == "ACTIVE"
            else start_from
        )
        user_subscription.end_date = start_from + timedelta(days=subscription_plan.duration_days)
        user_subscription.status = "ACTIVE"
        user_subscription.cancelled_at = None
        user_subscription.payment_status = (
            "FREE" if subscription_plan.price == 0 else "PAID"
        )

        if request.remarks:
            user_subscription.remarks = request.remarks

        await UserSubscriptionRepository.reset_usage(
            session=session,
            user_subscription_id=user_subscription.user_subscription_id,
        )
        updated = await UserSubscriptionService._repo_update(session, user_subscription)

        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=updated.user_subscription_id,
                subscription_id=updated.subscription_id,
                user_id=updated.user_id,
                action="RENEWED",
                performed_by=performed_by,
                old_start_date=old_start,
                old_end_date=old_end,
                new_start_date=updated.start_date,
                new_end_date=updated.end_date,
                remarks=request.remarks,
            ),
            commit=False,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=performed_by,
            action="SUBSCRIPTION_RENEWED",
            user_subscription=updated,
            plan=subscription_plan,
            description="Subscription renewed",
            remarks=request.remarks,
            metadata={
                "old_end_date": old_end.isoformat() if old_end else None,
                "new_end_date": updated.end_date.isoformat() if updated.end_date else None,
            },
        )
        await UserSubscriptionService._notify_subscription_event(
            session,
            user_subscription=updated,
            plan=subscription_plan,
            notification_type=NotificationType.SUBSCRIPTION_RENEWED,
            title="Subscription Renewed",
            message=(
                f"{getattr(subscription_plan, 'subscription_name', 'Subscription')} "
                "has been renewed."
            ),
            event_action="renewed",
        )
        await commit_rollback(session)
        return _response(updated, subscription_plan)

    # ==========================================
    # CANCEL SUBSCRIPTION
    # ==========================================

    @staticmethod
    async def cancel_subscription(
        session,
        user_id: UUID,
        request: CancelSubscriptionRequest,
        performed_by: UUID | None = None,
        user_subscription_id: UUID | None = None,
    ):

        subscription = None
        if user_subscription_id:
            subscription = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if subscription and subscription.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription:
            subscription = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )
        current_status = (subscription.status or "").upper()
        if "CANCELLED" not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change subscription from {current_status} to CANCELLED.",
            )

        old_start = subscription.start_date
        old_end = subscription.end_date
        if request.remarks:
            subscription.remarks = request.remarks
        subscription.cancelled_at = _utc_now_naive()

        cancelled = await UserSubscriptionService._repo_cancel(session, subscription)

        await UserSubscriptionRepository.add_history(
            session=session,
            history=SubscriptionHistory(
                user_subscription_id=cancelled.user_subscription_id,
                subscription_id=cancelled.subscription_id,
                user_id=cancelled.user_id,
                action="CANCELLED",
                performed_by=performed_by,
                old_start_date=old_start,
                old_end_date=old_end,
                new_start_date=cancelled.start_date,
                new_end_date=cancelled.end_date,
                remarks=request.remarks,
            ),
            commit=False,
        )
        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=cancelled.subscription_id,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=performed_by,
            action="SUBSCRIPTION_CANCELLED",
            user_subscription=cancelled,
            plan=plan,
            description="Subscription cancelled",
            remarks=request.remarks,
            metadata={
                "old_end_date": old_end.isoformat() if old_end else None,
            },
        )
        await commit_rollback(session)
        return _response(cancelled, plan)

    @staticmethod
    async def change_subscription(
        session,
        user_id: UUID,
        request: ChangeSubscriptionRequest,
        *,
        action: str,
        performed_by: UUID | None = None,
        user_subscription_id: UUID | None = None,
    ):
        action = action.upper()
        if action not in {"UPGRADED", "DOWNGRADED", "CHANGE_PLAN"}:
            raise HTTPException(status_code=400, detail="Invalid subscription change action.")

        current = None
        if user_subscription_id:
            current = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if current and current.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not current:
            current = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )
        if not current:
            current = await UserSubscriptionRepository.get_latest_subscription(
                session=session,
                user_id=user_id,
            )
        if not current:
            raise HTTPException(status_code=404, detail="Subscription not found.")

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=request.subscription_id,
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        if not plan.is_active:
            raise HTTPException(status_code=400, detail="Subscription plan is inactive.")

        old_start = current.start_date
        old_end = current.end_date
        old_subscription_id = current.subscription_id
        old_plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=current.subscription_id,
        )
        new_role = SubscriptionBootstrapService.normalize_subscription_role(
            plan.subscription_type
        )
        UserSubscriptionService._ensure_plan_matches_role(plan, new_role)
        await UserSubscriptionService._ensure_user_and_role(
            session=session,
            user_id=user_id,
            role=new_role,
        )
        conflicting = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
            role=new_role,
            exclude_user_subscription_id=current.user_subscription_id,
        )
        if (
            conflicting
            and conflicting.user_subscription_id != current.user_subscription_id
        ):
            raise HTTPException(
                status_code=409,
                detail=f"User already has an active {new_role} subscription.",
            )
        current = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=current,
        )
        is_final_subscription = current.status in FINAL_STATUSES
        if not is_final_subscription and current.status not in MUTABLE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"{current.status.title()} subscriptions cannot be changed.",
            )
        if old_plan:
            old_price = Decimal(str(getattr(old_plan, "price", 0) or 0))
            new_price = Decimal(str(getattr(plan, "price", 0) or 0))
            if action == "CHANGE_PLAN":
                action = "UPGRADED" if new_price >= old_price else "DOWNGRADED"
            if action == "UPGRADED" and new_price < old_price:
                raise HTTPException(
                    status_code=400,
                    detail="Upgrade target plan cannot be cheaper than the current plan.",
                )
            if action == "DOWNGRADED" and new_price > old_price:
                raise HTTPException(
                    status_code=400,
                    detail="Downgrade target plan cannot be more expensive than the current plan.",
                )

        now = _utc_now_naive()
        if is_final_subscription:
            current = UserSubscription(
                user_id=user_id,
                subscription_id=request.subscription_id,
                role=new_role,
                start_date=now,
                end_date=now + timedelta(days=plan.duration_days),
                status="ACTIVE",
                payment_status="FREE" if plan.price == 0 else "PAID",
                price_paid=plan.price,
                discount_amount=Decimal("0.00"),
                currency=plan.currency,
                auto_renew=False,
                assigned_by=performed_by,
                remarks=request.remarks,
            )
            updated = await UserSubscriptionService._repo_create(session, current)
        else:
            current.subscription_id = request.subscription_id
            current.role = new_role
            current.start_date = now
            current.end_date = now + timedelta(days=plan.duration_days)
            current.status = "ACTIVE"
            current.cancelled_at = None
            current.remarks = request.remarks or current.remarks
            updated = await UserSubscriptionService._repo_update(session, current)

        if request.reset_usage and not is_final_subscription:
            await UserSubscriptionRepository.reset_usage(
                session=session,
                user_subscription_id=updated.user_subscription_id,
            )

        await UserSubscriptionService._record_history(
            session=session,
            user_subscription=updated,
            action=action,
            performed_by=performed_by,
            old_start_date=old_start,
            old_end_date=old_end,
            remarks=request.remarks,
            commit=False,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=performed_by,
            action=f"SUBSCRIPTION_{action}",
            user_subscription=updated,
            plan=plan,
            description=f"Subscription {action.lower()}",
            remarks=request.remarks,
            metadata={
                "old_subscription_id": str(old_subscription_id),
                "new_subscription_id": str(updated.subscription_id),
            },
        )
        await commit_rollback(session)
        return _response(updated, plan)

    @staticmethod
    async def update_status(
        session,
        user_id: UUID,
        request: SubscriptionActionRequest,
        *,
        status: str,
        action: str,
        performed_by: UUID | None = None,
        user_subscription_id: UUID | None = None,
    ):
        status = status.upper()
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid subscription status.")

        subscription = None
        if user_subscription_id:
            subscription = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if subscription and subscription.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription:
            subscription = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )
        if not subscription:
            subscription = await UserSubscriptionRepository.get_latest_subscription(
                session=session,
                user_id=user_id,
            )
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found.")

        old_status = subscription.status
        current_status = (subscription.status or "").upper()
        if status not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change subscription from {current_status} to {status}.",
            )

        old_start = subscription.start_date
        old_end = subscription.end_date
        subscription.status = status
        if status == "ACTIVE":
            subscription.cancelled_at = None
            if subscription.end_date <= _utc_now_naive():
                plan = await SubscriptionRepository.get_by_id(
                    session=session,
                    subscription_id=subscription.subscription_id,
                )
                if not plan or not plan.is_active:
                    raise HTTPException(
                        status_code=400,
                        detail="Active subscription plan required.",
                    )
                subscription.start_date = _utc_now_naive()
                subscription.end_date = subscription.start_date + timedelta(
                    days=plan.duration_days,
                )
        elif status == "CANCELLED":
            subscription.cancelled_at = _utc_now_naive()
        if request.remarks:
            subscription.remarks = request.remarks

        updated = await UserSubscriptionService._repo_update(session, subscription)
        await UserSubscriptionService._record_history(
            session=session,
            user_subscription=updated,
            action=action,
            performed_by=performed_by,
            old_start_date=old_start,
            old_end_date=old_end,
            remarks=request.remarks,
            commit=False,
        )
        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=updated.subscription_id,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=performed_by,
            action=f"SUBSCRIPTION_{action}",
            user_subscription=updated,
            plan=plan,
            description=f"Subscription {action.lower()}",
            remarks=request.remarks,
            metadata={
                "old_status": old_status,
                "new_status": status,
                "old_end_date": old_end.isoformat() if old_end else None,
                "new_end_date": updated.end_date.isoformat() if updated.end_date else None,
            },
        )
        if status == "EXPIRED":
            assigned = await SubscriptionBootstrapService.ensure_user_subscription(
                session=session,
                user_id=updated.user_id,
                role=updated.role,
                assigned_by=performed_by,
                remarks="Assigned default subscription after expiration.",
            )
            if assigned.user_subscription_id != updated.user_subscription_id:
                plan = await SubscriptionRepository.get_by_id(
                    session=session,
                    subscription_id=assigned.subscription_id,
                )
                return _response(assigned, plan)
        await commit_rollback(session)
        return _response(updated, plan)

    @staticmethod
    async def get_usage_statistics(session, user_id: UUID):
        subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
        )
        if not subscription:
            subscription = await UserSubscriptionRepository.get_latest_subscription(
                session=session,
                user_id=user_id,
            )
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found.")
        usage = await UserSubscriptionRepository.list_usage(
            session=session,
            user_subscription_id=subscription.user_subscription_id,
        )
        return [SubscriptionUsageItem.model_validate(item) for item in usage]

    @staticmethod
    async def get_remaining_usage(
        session,
        user_id: UUID,
        user_subscription_id: UUID | None = None,
    ):
        subscription = None
        if user_subscription_id:
            subscription = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if subscription and subscription.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription:
            subscription = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )
        subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=subscription,
            assign_default=user_subscription_id is None,
        )
        if not subscription or subscription.status != "ACTIVE":
            raise HTTPException(status_code=404, detail="No active subscription found.")

        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription.subscription_id,
        )
        features = _subscription_features(plan) if plan else {}
        usage_rows = await UserSubscriptionRepository.list_usage(
            session=session,
            user_subscription_id=subscription.user_subscription_id,
        )
        usage_by_feature = {}
        current_week_start, current_week_end = _current_week_window()
        for item in usage_rows:
            if str(item.feature_name).endswith("_per_week"):
                if (
                    item.period_start != current_week_start
                    or item.period_end != current_week_end
                ):
                    continue
            usage_by_feature[item.feature_name] = (
                usage_by_feature.get(item.feature_name, 0) + int(item.used_count)
            )
        limit_features = {
            key
            for key, value in features.items()
            if value not in (True, False, None, "", "-", "unlimited", "UNLIMITED")
        } | set(usage_by_feature)

        items = []
        for feature_name in sorted(limit_features):
            period_start = current_week_start if feature_name.endswith("_per_week") else None
            period_end = current_week_end if feature_name.endswith("_per_week") else None
            raw_limit = features.get(feature_name)
            try:
                limit = None if raw_limit in (None, "", "-", "unlimited", "UNLIMITED") else int(raw_limit)
            except (TypeError, ValueError):
                limit = None
            used = usage_by_feature.get(feature_name, 0)
            items.append(
                RemainingUsageItem(
                    feature_name=feature_name,
                    period_start=period_start,
                    period_end=period_end,
                    used_count=used,
                    limit=limit,
                    remaining=None if limit is None else max(limit - used, 0),
                    unlimited=limit is None,
                )
            )
        return RemainingUsageResponse(
            user_subscription_id=subscription.user_subscription_id,
            subscription_id=subscription.subscription_id,
            usage=items,
        )

    @staticmethod
    async def reset_usage(
        session,
        user_id: UUID,
        request: UsageResetRequest,
        performed_by: UUID | None = None,
        user_subscription_id: UUID | None = None,
    ):
        subscription = None
        if user_subscription_id:
            subscription = await UserSubscriptionRepository.get_by_id(
                session=session,
                user_subscription_id=user_subscription_id,
            )
            if subscription and subscription.user_id != user_id:
                raise HTTPException(status_code=404, detail="Subscription not found.")
        if not subscription:
            subscription = await UserSubscriptionRepository.get_active_subscription(
                session=session,
                user_id=user_id,
            )
        if not subscription:
            raise HTTPException(status_code=404, detail="No active subscription found.")
        await UserSubscriptionRepository.reset_usage(
            session=session,
            user_subscription_id=subscription.user_subscription_id,
            feature_name=request.feature_name,
        )
        await UserSubscriptionService._record_history(
            session=session,
            user_subscription=subscription,
            action="USAGE_RESET",
            performed_by=performed_by,
            remarks=(
                f"Reset usage for {request.feature_name}."
                if request.feature_name
                else "Reset all usage counters."
            ),
            commit=False,
        )
        await session.commit()
        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription.subscription_id,
        )
        await UserSubscriptionService._log_user_subscription_activity(
            session,
            performed_by=performed_by,
            action="SUBSCRIPTION_USAGE_RESET",
            user_subscription=subscription,
            plan=plan,
            description="Subscription usage reset",
            remarks=(
                f"Reset usage for {request.feature_name}."
                if request.feature_name
                else "Reset all usage counters."
            ),
            metadata={"feature_name": request.feature_name},
        )
        return await UserSubscriptionService.get_remaining_usage(
            session=session,
            user_id=user_id,
            user_subscription_id=subscription.user_subscription_id,
        )

    # ==========================================
    # GET SUBSCRIPTION BY ID
    # ==========================================

    @staticmethod
    async def get_by_id(
        session,
        user_subscription_id: UUID,
    ):

        subscription = await UserSubscriptionRepository.get_by_id(
            session=session,
            user_subscription_id=user_subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=subscription,
        )
        plan = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription.subscription_id,
        )
        return _response(subscription, plan)

    @staticmethod
    async def get_details(
        session,
        user_subscription_id: UUID,
    ):
        logger.info(
            "Fetching subscription details for user_subscription_id=%s",
            user_subscription_id,
        )
        try:
            row = await UserSubscriptionRepository.get_by_id_with_details(
                session=session,
                user_subscription_id=user_subscription_id,
            )
        except Exception as exc:
            logger.exception(
                "Failed to fetch subscription details for user_subscription_id=%s",
                user_subscription_id,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch subscription details.",
            ) from exc

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        subscription, user, plan = row
        subscription = await UserSubscriptionService._expire_if_needed(
            session=session,
            user_subscription=subscription,
        )
        return _details_response(subscription, user, plan)

    @staticmethod
    async def list_subscribers(
        session,
        *,
        active: bool,
        role: str | None = None,
    ):
        rows = await UserSubscriptionRepository.list_by_active_state(
            session=session,
            active=active,
            role=role,
        )
        return [
            _response(user_subscription, subscription, user)
            for user_subscription, subscription, user in rows
        ]
