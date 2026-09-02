from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from app.utils.utc import utc_now_naive

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.subscription.subscription import Subscription
from app.model.subscription.subscription_history import SubscriptionHistory
from app.model.subscription.user_subscription import UserSubscription
from app.repository.super_admin.settings_repo import SystemSettingsRepository
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.repository.subscription.user_subscription_repo import (
    UserSubscriptionRepository,
)


DEFAULT_PLAN_NAMES = {
    "CANDIDATE": "Default Candidate Plan",
    "EMPLOYER": "Default Employer Plan",
}

CANDIDATE_DEFAULT_FEATURES = {
    "job_alerts": True,
    "max_job_alerts": None,
    "recruiters_can_contact_candidate": True,
    "resume_builder": True,
    "resume_visibility": True,
    "saved_jobs": True,
    "saved_jobs_limit": 30,
}

EMPLOYER_DEFAULT_FEATURES = {
    "ai_job_description_generator": True,
    "ai_job_description_generations_per_month": None,
    "ai_candidate_matching": True,
    "ai_candidate_matching_runs_per_month": None,
    "ai_candidate_analyses_per_month": None,
    "ai_candidate_insights": True,
    "ai_candidate_insights_per_month": None,
    "ai_message_drafting": True,
    "ai_message_drafts_per_month": None,
    "candidate_invitations": True,
    "candidate_invitations_per_week": None,
    "candidate_search": True,
    "ai_applicant_ranking": False,
}

DEFAULT_FEATURES_BY_ROLE = {
    "CANDIDATE": CANDIDATE_DEFAULT_FEATURES,
    "EMPLOYER": EMPLOYER_DEFAULT_FEATURES,
}

DEFAULT_LIMITS_BY_ROLE = {
    "CANDIDATE": {
        "max_resume_uploads": 5,
    },
}

ROLE_CODES_BY_SUBSCRIPTION_ROLE = {
    "CANDIDATE": {"ROLE_CANDIDATE"},
    "EMPLOYER": {"ROLE_EMPLOYER", "ROLE_RECRUITER", "ROLE_ADMIN"},
}


class SubscriptionBootstrapService:
    @staticmethod
    def normalize_subscription_role(role: str) -> str:
        role = (role or "").upper().replace("ROLE_", "")
        if role in {"EMPLOYER", "RECRUITER", "ADMIN"}:
            return "EMPLOYER"
        return role

    @staticmethod
    def _merge_enabled_features(
        existing: dict | None,
        features: dict | None,
    ) -> dict:
        merged = dict(existing or {})
        merged.update(features or {})
        return dict(sorted(merged.items()))

    @staticmethod
    def discover_default_features(role: str) -> dict:
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        return dict(DEFAULT_FEATURES_BY_ROLE.get(role, {}))

    @staticmethod
    async def ensure_default_subscription_settings(
        session: AsyncSession,
        *,
        candidate_plan: Subscription,
        employer_plan: Subscription,
    ):
        settings = await SystemSettingsRepository.get_active(session)
        if settings is None:
            settings = await SystemSettingsRepository.create_default(session)
        settings.candidate_default_subscription_plan = str(
            candidate_plan.subscription_id
        )
        settings.employer_default_subscription_plan = str(
            employer_plan.subscription_id
        )
        settings.default_subscription_plan = str(candidate_plan.subscription_id)
        settings.updated_at = utc_now_naive()
        session.add(settings)
        return settings

    @staticmethod
    async def ensure_default_plan(
        session: AsyncSession,
        role: str,
        *,
        features: dict | None = None,
    ) -> Subscription:
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        features = {
            **SubscriptionBootstrapService.discover_default_features(role),
            **(features or {}),
        }
        plan = await SubscriptionRepository.get_default(
            session=session,
            subscription_type=role,
        )
        if plan is None:
            existing = await SubscriptionRepository.exists_by_name(
                session=session,
                name=DEFAULT_PLAN_NAMES[role],
            )
            if existing:
                plan = existing
            else:
                plan = Subscription(
                    subscription_name=DEFAULT_PLAN_NAMES[role],
                    subscription_type=role,
                    description=f"System default {role.lower()} subscription plan.",
                    price=Decimal("0.00"),
                    currency="INR",
                    duration_days=3650,
                    billing_cycle="Monthly",
                    display_order=999,
                    feature_flags=dict(features or {}),
                    is_active=True,
                    is_default=True,
                    is_popular=False,
                )
                session.add(plan)
                await session.flush()

        await SubscriptionRepository.clear_default_for_type(
            session=session,
            subscription_type=role,
            exclude_subscription_id=plan.subscription_id,
        )
        plan.subscription_type = role
        plan.price = Decimal("0.00") if plan.price is None else plan.price
        for field, value in DEFAULT_LIMITS_BY_ROLE.get(role, {}).items():
            setattr(plan, field, value)
        plan.is_active = True
        plan.is_default = True
        plan.feature_flags = SubscriptionBootstrapService._merge_enabled_features(
            plan.feature_flags,
            features,
        )
        plan.updated_at = utc_now_naive()
        session.add(plan)
        return plan

    @staticmethod
    async def get_assignment_default_plan(
        session: AsyncSession,
        role: str,
        *,
        features: dict | None = None,
    ) -> Subscription:
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        settings = await SystemSettingsRepository.get_active(session)
        role_default_field = (
            "candidate_default_subscription_plan"
            if role == "CANDIDATE"
            else "employer_default_subscription_plan"
        )
        configured_plan_id = getattr(settings, role_default_field, None)
        configured_plan_id = configured_plan_id or getattr(
            settings,
            "default_subscription_plan",
            None,
        )
        if configured_plan_id:
            try:
                configured_plan_uuid = UUID(str(configured_plan_id))
            except ValueError:
                configured_plan_uuid = None
            if configured_plan_uuid:
                plan = await SubscriptionRepository.get_by_id(
                    session=session,
                    subscription_id=configured_plan_uuid,
                )
                if (
                    plan
                    and plan.is_active
                    and SubscriptionBootstrapService.normalize_subscription_role(
                        plan.subscription_type
                    )
                    == role
                ):
                    return plan

        return await SubscriptionBootstrapService.ensure_default_plan(
            session=session,
            role=role,
            features=features,
        )

    @staticmethod
    async def ensure_user_subscription(
        session: AsyncSession,
        *,
        user_id: UUID,
        role: str,
        assigned_by: UUID | None = None,
        remarks: str | None = None,
        commit: bool = True,
    ) -> UserSubscription:
        role = SubscriptionBootstrapService.normalize_subscription_role(role)
        existing = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=user_id,
            role=role,
        )
        if existing:
            return existing

        plan = await SubscriptionBootstrapService.get_assignment_default_plan(
            session=session,
            role=role,
        )
        now = utc_now_naive()
        user_subscription = UserSubscription(
            user_id=user_id,
            subscription_id=plan.subscription_id,
            role=role,
            start_date=now,
            end_date=now + timedelta(days=plan.duration_days),
            status="ACTIVE",
            payment_status="FREE" if plan.price == 0 else "PAID",
            price_paid=plan.price,
            discount_amount=Decimal("0.00"),
            currency=plan.currency,
            assigned_by=assigned_by,
            remarks=remarks,
        )
        session.add(user_subscription)
        await session.flush()
        session.add(
            SubscriptionHistory(
                user_subscription_id=user_subscription.user_subscription_id,
                subscription_id=user_subscription.subscription_id,
                user_id=user_subscription.user_id,
                action="ASSIGNED",
                performed_by=assigned_by,
                new_start_date=user_subscription.start_date,
                new_end_date=user_subscription.end_date,
                remarks=remarks or "Assigned default subscription plan.",
            )
        )
        if commit:
            await commit_rollback(session)
            await session.refresh(user_subscription)
        return user_subscription

    @staticmethod
    async def backfill_missing_user_subscriptions(
        session: AsyncSession,
    ) -> int:
        assigned = 0
        for role, role_codes in ROLE_CODES_BY_SUBSCRIPTION_ROLE.items():
            rows = await UserSubscriptionRepository.list_users_missing_active_subscription(
                session=session,
                role_codes=role_codes,
                subscription_role=role,
            )
            seen_user_ids = set()
            for user, _role_code in rows:
                if user.user_id in seen_user_ids:
                    continue
                seen_user_ids.add(user.user_id)
                await SubscriptionBootstrapService.ensure_user_subscription(
                    session=session,
                    user_id=user.user_id,
                    role=role,
                    remarks="Backfilled default subscription plan.",
                    commit=False,
                )
                assigned += 1
        return assigned

    @staticmethod
    async def bootstrap_defaults_and_assignments(
        session: AsyncSession,
        app=None,
    ) -> dict:
        candidate_plan = await SubscriptionBootstrapService.ensure_default_plan(
            session=session,
            role="CANDIDATE",
        )
        employer_plan = await SubscriptionBootstrapService.ensure_default_plan(
            session=session,
            role="EMPLOYER",
        )
        await SubscriptionBootstrapService.ensure_default_subscription_settings(
            session=session,
            candidate_plan=candidate_plan,
            employer_plan=employer_plan,
        )

        assigned = await SubscriptionBootstrapService.backfill_missing_user_subscriptions(
            session=session,
        )

        await commit_rollback(session)
        return {
            "features_discovered": (
                len(SubscriptionBootstrapService.discover_default_features("CANDIDATE"))
                + len(SubscriptionBootstrapService.discover_default_features("EMPLOYER"))
            ),
            "candidate_default_plan": candidate_plan.subscription_id,
            "employer_default_plan": employer_plan.subscription_id,
            "subscriptions_assigned": assigned,
        }
