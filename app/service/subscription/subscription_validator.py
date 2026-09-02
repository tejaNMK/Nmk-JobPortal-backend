from datetime import datetime, timedelta
from uuid import UUID
from app.utils.utc import utc_now_naive

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.service.subscription.subscription_bootstrap_service import (
    SubscriptionBootstrapService,
)
from app.service.subscription.user_subscription_service import (
    UserSubscriptionService,
    _subscription_features,
)


class SubscriptionValidator:
    FEATURE_LIMIT_ALIASES = {
        "candidate_invitations": "candidate_invitations",
        "saved_jobs": "saved_jobs_limit",
    }
    FEATURE_LABELS = {
        "candidate_invitations": "candidate invitations",
        "candidate_search": "candidate search",
        "ai_applicant_ranking": "AI applicant ranking",
        "ai_applicant_ranking": "AI applicant ranking",
        "ai_message_drafting": "AI-assisted message drafting",
        "ai_job_description_generator": "AI job description generator",
        "ai_candidate_matching": "AI candidate matching",
        "ai_candidate_insights": "AI candidate insights",
        "job_alerts": "job alerts",
        "recruiters_can_contact_candidate": "recruiter contact access",
        "resume_builder": "resume builder",
        "resume_visibility": "Open to Work visibility",
        "saved_jobs": "saved jobs",
    }

    def __init__(self, session: AsyncSession, user_id: UUID, role: str | None = None):
        self.session = session
        self.user_id = UUID(str(user_id))
        self.role = (
            SubscriptionBootstrapService.normalize_subscription_role(role)
            if role
            else None
        )
        self._user_subscription = None
        self._subscription = None
        self._features = None

    @staticmethod
    def _period_window(period: str | None):
        if period is None:
            return None, None
        normalized = period.strip().lower()
        if normalized not in {"week", "month"}:
            raise HTTPException(
                status_code=400,
                detail="Unsupported subscription usage period.",
            )
        now = utc_now_naive()
        if normalized == "month":
            month_start = datetime(now.year, now.month, 1)
            if now.month == 12:
                month_end = datetime(now.year + 1, 1, 1)
            else:
                month_end = datetime(now.year, now.month + 1, 1)
            return month_start, month_end
        week_start = datetime(now.year, now.month, now.day) - timedelta(
            days=now.weekday()
        )
        return week_start, week_start + timedelta(days=7)

    async def validate_active_subscription(self):
        if self._user_subscription is None:
            user_subscription = await UserSubscriptionRepository.get_active_subscription(
                session=self.session,
                user_id=self.user_id,
                role=self.role,
            )
            user_subscription = await UserSubscriptionService._expire_if_needed(
                session=self.session,
                user_subscription=user_subscription,
                assign_default=True,
            )
            if not user_subscription and self.role:
                user_subscription = await SubscriptionBootstrapService.ensure_user_subscription(
                    session=self.session,
                    user_id=self.user_id,
                    role=self.role,
                    remarks="Assigned default subscription during permission check.",
                )
            if not user_subscription or user_subscription.status != "ACTIVE":
                raise HTTPException(
                    status_code=403,
                    detail="Active subscription required.",
                )
            self._user_subscription = user_subscription

        return self._user_subscription

    async def _load_subscription(self):
        if self._subscription is None:
            user_subscription = await self.validate_active_subscription()
            subscription = await SubscriptionRepository.get_by_id(
                session=self.session,
                subscription_id=user_subscription.subscription_id,
            )
            if not subscription or not subscription.is_active:
                raise HTTPException(
                    status_code=403,
                    detail="Active subscription plan required.",
                )
            UserSubscriptionService._ensure_plan_matches_role(
                subscription,
                user_subscription.role,
            )
            self._subscription = subscription
        return self._subscription

    async def _load_features(self) -> dict:
        if self._features is None:
            subscription = await self._load_subscription()
            self._features = _subscription_features(subscription)
        return self._features

    async def has_feature(self, feature_name: str) -> bool:
        features = await self._load_features()
        value = features.get(feature_name)
        if value is None and feature_name in self.FEATURE_LIMIT_ALIASES:
            value = features.get(self.FEATURE_LIMIT_ALIASES[feature_name])
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized_value = value.strip().lower()
            if normalized_value in {"true", "yes", "enabled", "unlimited"}:
                return True
            try:
                return int(normalized_value) != 0
            except ValueError:
                return False
        return bool(value)

    async def require_feature(self, feature_name: str) -> None:
        if not await self.has_feature(feature_name):
            feature_label = self.FEATURE_LABELS.get(
                feature_name,
                feature_name.replace("_", " "),
            )
            raise HTTPException(
                status_code=403,
                detail=f"Your current subscription does not include {feature_label}.",
            )

    async def get_limit(self, limit_name: str) -> int | None:
        features = await self._load_features()
        value = features.get(limit_name)
        if value in (None, "", "-", "unlimited", "UNLIMITED"):
            return None
        if isinstance(value, bool):
            return None
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return None
        return limit if limit >= 0 else None

    async def _used_count(self, limit_name: str, *, period: str | None = None) -> int:
        user_subscription = await self.validate_active_subscription()
        period_start, period_end = self._period_window(period)
        usage = await UserSubscriptionRepository.get_usage(
            session=self.session,
            user_subscription_id=user_subscription.user_subscription_id,
            feature_name=limit_name,
            period_start=period_start,
            period_end=period_end,
        )
        return int(usage.used_count) if usage else 0

    async def remaining_limit(
        self,
        limit_name: str,
        *,
        period: str | None = None,
    ) -> int | None:
        limit = await self.get_limit(limit_name)
        if limit is None:
            return None
        return max(limit - await self._used_count(limit_name, period=period), 0)

    async def ensure_limit_available(
        self,
        limit_name: str,
        *,
        current_usage: int | None = None,
        amount: int = 1,
        period: str | None = None,
    ) -> None:
        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Usage amount must be positive.",
            )
        limit = await self.get_limit(limit_name)
        if limit is None:
            return
        used = (
            current_usage
            if current_usage is not None
            else await self._used_count(limit_name, period=period)
        )
        if used + amount > limit:
            raise HTTPException(
                status_code=403,
                detail=f"Subscription limit reached for {limit_name}.",
            )

    async def consume_limit(
        self,
        limit_name: str,
        amount: int = 1,
        *,
        period: str | None = None,
    ):
        await self.ensure_limit_available(limit_name, amount=amount, period=period)
        user_subscription = await self.validate_active_subscription()
        period_start, period_end = self._period_window(period)
        return await UserSubscriptionRepository.increment_usage(
            session=self.session,
            user_subscription_id=user_subscription.user_subscription_id,
            user_id=self.user_id,
            feature_name=limit_name,
            amount=amount,
            period_start=period_start,
            period_end=period_end,
        )
