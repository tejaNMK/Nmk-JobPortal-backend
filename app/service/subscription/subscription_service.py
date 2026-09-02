from uuid import UUID

from fastapi import HTTPException

from app.model.subscription.subscription import Subscription
from app.repository.authentication.users import UsersRepository
from app.repository.super_admin.settings_repo import SystemSettingsRepository
from app.repository.subscription.subscription_repo import SubscriptionRepository
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.schema.subscription.subscription import (
    SubscriptionCatalogueResponse,
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService


UI_FEATURE_KEYS = {
    "resume_builder",
    "resume_visibility",
    "job_alerts",
    "recruiters_can_contact_candidate",
    "saved_jobs_limit",
    "saved_jobs",
    "candidate_invitations",
    "candidate_invitations_per_week",
    "candidate_search",
    "ai_applicant_ranking",
    "ai_applicant_ranking",
    "ai_job_description_generator",
    "ai_job_description_generations_per_month",
    "ai_candidate_matching",
    "ai_candidate_matching_runs_per_month",
    "ai_candidate_analyses_per_month",
    "ai_candidate_insights",
    "ai_candidate_insights_per_month",
    "ai_message_drafting",
    "ai_message_drafts_per_month",
}
FEATURE_LIMIT_RESPONSE_FIELDS = {
    "saved_jobs_limit",
    "candidate_invitations_per_week",
    "ai_job_description_generations_per_month",
    "ai_candidate_matching_runs_per_month",
    "ai_candidate_analyses_per_month",
    "ai_candidate_insights_per_month",
    "ai_message_drafts_per_month",
}
FEATURE_TOGGLE_RESPONSE_FIELDS = {
    "candidate_invitations",
    "ai_applicant_ranking",
}
REMOVED_FEATURE_KEYS = {
    "company_profile",
    "job_posting",
    "max_active_job_posts",
    "max_candidate_searches",
    "max_job_applications",
    "resume_downloads",
    "resume_upload",
    "unlimited_job_posts",
    "unlimited_job_applications",
}
WRITABLE_SUBSCRIPTION_FIELDS = {
    "subscription_name",
    "subscription_type",
    "description",
    "price",
    "currency",
    "duration_days",
    "billing_cycle",
    "display_order",
    "max_published_jobs",
    "max_job_alerts",
    "max_resume_uploads",
    "feature_flags",
    "is_featured",
    "is_popular",
    "is_active",
    "is_default",
    "created_by",
    "updated_by",
}
FIELD_ALIASES = {
    "popular_plan": "is_popular",
    "active": "is_active",
}


def _normalize_key(key: str) -> str:
    normalized = []
    previous = ""
    for char in str(key).strip():
        if char.isupper() and previous and (previous.islower() or previous.isdigit()):
            normalized.append("_")
        if char.isalnum():
            normalized.append(char.lower())
        else:
            normalized.append("_")
        previous = char
    return "_".join("".join(normalized).split("_"))


def _flatten_features(features: dict | None) -> dict:
    flattened = {}
    for key, value in (features or {}).items():
        normalized_key = _normalize_key(key)
        if isinstance(value, dict):
            flattened.update(_flatten_features(value))
        elif normalized_key not in REMOVED_FEATURE_KEYS:
            flattened[normalized_key] = value
    return flattened


def _status_to_is_active(status) -> bool:
    if isinstance(status, bool):
        return status
    if isinstance(status, str):
        return status.strip().lower() in {"active", "enabled", "true", "1", "yes"}
    return bool(status)


def _feature_limit_value(feature_map: dict, key: str):
    value = feature_map.get(key)
    if value in (None, "", "-", "unlimited", "UNLIMITED"):
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if limit >= 0 else None


def _feature_toggle_value(feature_map: dict, key: str):
    value = feature_map.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "enabled", "1"}
    return bool(value)


def _visible_feature_map(feature_map: dict) -> dict:
    return {
        normalized_key: value
        for normalized_key, value in _flatten_features(feature_map).items()
        if normalized_key in UI_FEATURE_KEYS
        and normalized_key not in FEATURE_LIMIT_RESPONSE_FIELDS
    }


class SubscriptionService:
    @staticmethod
    def _role_codes_from_user(user) -> set[str]:
        return {
            str(getattr(role, "role_code", "") or getattr(role, "role_name", "")).upper()
            for role in getattr(user, "roles", []) or []
            if getattr(role, "role_code", None) or getattr(role, "role_name", None)
        }

    @staticmethod
    def _subscription_type_for_role_codes(role_codes: set[str]) -> str | None:
        employer_roles = {"ROLE_EMPLOYER", "ROLE_RECRUITER", "ROLE_ADMIN"}
        if role_codes.intersection(employer_roles):
            return "EMPLOYER"
        if "ROLE_CANDIDATE" in role_codes:
            return "CANDIDATE"
        return None

    @staticmethod
    def _settings_field_for_subscription_type(subscription_type: str) -> str:
        normalized_type = (subscription_type or "").upper()
        if normalized_type == "CANDIDATE":
            return "candidate_default_subscription_plan"
        return "employer_default_subscription_plan"

    @staticmethod
    async def _sync_default_setting(session, subscription: Subscription) -> None:
        settings = await SystemSettingsRepository.get_active(session)
        if not settings:
            settings = await SystemSettingsRepository.create_default(session)
        field = SubscriptionService._settings_field_for_subscription_type(
            subscription.subscription_type
        )
        setattr(settings, field, str(subscription.subscription_id))
        if field == "candidate_default_subscription_plan":
            settings.default_subscription_plan = str(subscription.subscription_id)
        session.add(settings)

    @staticmethod
    async def _log_plan_activity(
        session,
        *,
        actor,
        action: str,
        subscription: Subscription,
        description: str,
        metadata: dict | None = None,
    ) -> None:
        if not actor:
            return
        await ActivityLogService.create_log(
            session=session,
            actor=actor,
            action=action,
            entity_type="SUBSCRIPTION",
            entity_id=str(subscription.subscription_id),
            target_entity_name=subscription.subscription_name,
            description=description,
            metadata=metadata,
        )

    @staticmethod
    async def _response(session, subscription: Subscription) -> SubscriptionResponse:
        data = SubscriptionResponse.model_validate(subscription).model_dump()
        raw_feature_map = dict(subscription.feature_flags or {})
        normalized_feature_map = _flatten_features(raw_feature_map)
        feature_map = _visible_feature_map(raw_feature_map)
        data["features"] = feature_map
        data["feature_flags"] = feature_map
        for key in FEATURE_LIMIT_RESPONSE_FIELDS:
            data[key] = _feature_limit_value(normalized_feature_map, key)
        for key in FEATURE_TOGGLE_RESPONSE_FIELDS:
            data[key] = _feature_toggle_value(normalized_feature_map, key)
        return SubscriptionResponse(**data)

    @staticmethod
    async def _catalogue_response(
        subscription: Subscription,
        *,
        current_subscription_id: UUID | None = None,
    ) -> SubscriptionCatalogueResponse:
        data = SubscriptionCatalogueResponse.model_validate(subscription).model_dump()
        raw_feature_map = dict(subscription.feature_flags or {})
        normalized_feature_map = _flatten_features(raw_feature_map)
        feature_map = _visible_feature_map(raw_feature_map)
        data["features"] = feature_map
        data["feature_flags"] = feature_map
        for key in FEATURE_LIMIT_RESPONSE_FIELDS:
            data[key] = _feature_limit_value(normalized_feature_map, key)
        for key in FEATURE_TOGGLE_RESPONSE_FIELDS:
            data[key] = _feature_toggle_value(normalized_feature_map, key)
        data["is_current"] = subscription.subscription_id == current_subscription_id
        return SubscriptionCatalogueResponse(**data)

    @staticmethod
    def _request_data(request) -> dict:
        request_data = request.model_dump(exclude_unset=True)
        request_data = {
            FIELD_ALIASES.get(_normalize_key(key), _normalize_key(key)): value
            for key, value in request_data.items()
        }
        status = request_data.pop("status", None)
        if status is not None:
            request_data["is_active"] = _status_to_is_active(status)

        ui_features = {
            key: request_data.pop(key)
            for key in list(request_data.keys())
            if key in UI_FEATURE_KEYS
        }
        incoming_features = request_data.pop("features", None)
        merged_features = _flatten_features(request_data.get("feature_flags") or {})
        if incoming_features is not None:
            merged_features.update(_flatten_features(incoming_features))
        merged_features.update(ui_features)
        if "feature_flags" in request_data or incoming_features is not None or ui_features:
            request_data["feature_flags"] = merged_features
        return {
            key: value
            for key, value in request_data.items()
            if key in WRITABLE_SUBSCRIPTION_FIELDS
        }

    @staticmethod
    async def create(
        session,
        request: SubscriptionCreate,
        actor=None,
    ):

        existing = await SubscriptionRepository.exists_by_name(
            session=session,
            name=request.subscription_name,
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Subscription name already exists.",
            )

        request_data = SubscriptionService._request_data(request)
        if not request_data.get("feature_flags"):
            request_data["feature_flags"] = {}

        subscription = Subscription(**request_data)

        if subscription.is_default:
            if not subscription.is_active:
                raise HTTPException(
                    status_code=400,
                    detail="Inactive subscription plans cannot be default.",
                )
            await SubscriptionRepository.clear_default_for_type(
                session=session,
                subscription_type=subscription.subscription_type,
            )

        subscription = await SubscriptionRepository.create(
            session=session,
            subscription=subscription,
        )
        await SubscriptionService._log_plan_activity(
            session,
            actor=actor,
            action="SUBSCRIPTION_CREATED",
            subscription=subscription,
            description=f"Subscription plan {subscription.subscription_name} created",
            metadata={
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
        )
        if subscription.is_default:
            await SubscriptionService._sync_default_setting(session, subscription)
            subscription = await SubscriptionRepository.update(
                session=session,
                subscription=subscription,
            )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="SUBSCRIPTION_CREATED",
            title="Subscription created",
            message=f"Subscription plan {subscription.subscription_name} was created.",
            entity_type="subscription",
            entity_id=str(subscription.subscription_id),
            target_route=f"/super-admin/subscriptions/{subscription.subscription_id}",
            metadata={
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
            event_key=f"subscription_created:{subscription.subscription_id}",
            commit=True,
        )

        return await SubscriptionService._response(session, subscription)

    @staticmethod
    async def get_all(
        session,
        *,
        subscription_type: str | None = None,
        status: str | None = None,
        billing_cycle: str | None = None,
        search: str | None = None,
    ):

        subscriptions = await SubscriptionRepository.get_all(
            session=session,
            subscription_type=subscription_type,
            status=status,
            billing_cycle=billing_cycle,
            search=search,
        )

        return [
            await SubscriptionService._response(session, subscription)
            for subscription in subscriptions
        ]

    @staticmethod
    async def get_available_for_user(
        session,
        *,
        user_id: UUID,
    ):
        user = await UsersRepository.find_by_user_id(
            session=session,
            user_id=str(user_id),
        )

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found.",
            )

        subscription_type = SubscriptionService._subscription_type_for_role_codes(
            SubscriptionService._role_codes_from_user(user)
        )

        if not subscription_type:
            raise HTTPException(
                status_code=400,
                detail="User role is not eligible for subscription plans.",
            )

        subscriptions = await SubscriptionRepository.get_all(
            session=session,
            subscription_type=subscription_type,
            status="active",
        )
        return [
            await SubscriptionService._response(session, subscription)
            for subscription in subscriptions
            if str(getattr(subscription, "subscription_type", "")).upper()
            == subscription_type
        ]

    @staticmethod
    async def get_catalogue_for_payload(
        session,
        *,
        payload,
        subscription_type: str | None = None,
        status: str | None = None,
        billing_cycle: str | None = None,
        search: str | None = None,
    ):
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = await UsersRepository.find_by_user_id(
            session=session,
            user_id=str(user_id),
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        role_codes = SubscriptionService._role_codes_from_user(user)
        normalized_type = subscription_type.strip().upper() if subscription_type else None
        normalized_status = status.strip().lower() if status else None

        if "ROLE_SUPER_ADMIN" in role_codes:
            subscriptions = await SubscriptionRepository.get_all(
                session=session,
                subscription_type=normalized_type,
                status=status,
                billing_cycle=billing_cycle,
                search=search,
            )
            return [
                await SubscriptionService._catalogue_response(subscription)
                for subscription in subscriptions
            ]

        allowed_type = SubscriptionService._subscription_type_for_role_codes(role_codes)
        if not allowed_type:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access subscription plans.",
            )

        if normalized_type and normalized_type != allowed_type:
            raise HTTPException(
                status_code=403,
                detail=f"{allowed_type.title()} users can only access active {allowed_type} plans.",
            )
        if normalized_status and normalized_status != "active":
            raise HTTPException(
                status_code=403,
                detail=f"{allowed_type.title()} users can only access active {allowed_type} plans.",
            )

        active_subscription = await UserSubscriptionRepository.get_active_subscription(
            session=session,
            user_id=UUID(str(user_id)),
            role=allowed_type,
        )
        current_subscription_id = (
            active_subscription.subscription_id if active_subscription else None
        )
        subscriptions = await SubscriptionRepository.get_all(
            session=session,
            subscription_type=allowed_type,
            status="active",
            billing_cycle=billing_cycle,
            search=search,
        )
        return [
            await SubscriptionService._catalogue_response(
                subscription,
                current_subscription_id=current_subscription_id,
            )
            for subscription in subscriptions
        ]

    @staticmethod
    async def get_by_id(
        session,
        subscription_id: UUID,
    ):

        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        return await SubscriptionService._response(session, subscription)

    @staticmethod
    async def update(
        session,
        subscription_id: UUID,
        request: SubscriptionUpdate,
        actor=None,
    ):

        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        update_data = SubscriptionService._request_data(request)
        if "feature_flags" in update_data:
            update_data["feature_flags"] = {
                **_flatten_features(subscription.feature_flags or {}),
                **update_data["feature_flags"],
            }
        new_subscription_type = update_data.get(
            "subscription_type",
            subscription.subscription_type,
        )
        if (
            new_subscription_type
            and new_subscription_type != subscription.subscription_type
        ):
            assignment_count = await SubscriptionRepository.count_user_assignments(
                session=session,
                subscription_id=subscription.subscription_id,
            )
            if assignment_count:
                raise HTTPException(
                    status_code=400,
                    detail="Subscription type cannot be changed while the plan is assigned to users.",
                )
        if update_data.get("is_default") is True:
            if update_data.get("is_active", subscription.is_active) is False:
                raise HTTPException(
                    status_code=400,
                    detail="Inactive subscription plans cannot be default.",
                )
            await SubscriptionRepository.clear_default_for_type(
                session=session,
                subscription_type=new_subscription_type,
                exclude_subscription_id=subscription.subscription_id,
            )
        if update_data.get("is_default") is False and subscription.is_default:
            raise HTTPException(
                status_code=400,
                detail="Default subscription plans cannot be unset directly. Set another active plan as default instead.",
            )
        if update_data.get("is_active") is False and (
            update_data.get("is_default", subscription.is_default) is True
        ):
            raise HTTPException(
                status_code=400,
                detail="Default subscription plans must remain active.",
            )

        for field, value in update_data.items():
            setattr(
                subscription,
                field,
                value,
            )

        subscription = await SubscriptionRepository.update(
            session=session,
            subscription=subscription,
        )
        if subscription.is_default:
            await SubscriptionService._sync_default_setting(session, subscription)
            subscription = await SubscriptionRepository.update(
                session=session,
                subscription=subscription,
            )
        await SubscriptionService._log_plan_activity(
            session,
            actor=actor,
            action="SUBSCRIPTION_UPDATED",
            subscription=subscription,
            description=f"Subscription plan {subscription.subscription_name} updated",
            metadata={
                "updated_fields": sorted(update_data.keys()),
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
        )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="SUBSCRIPTION_UPDATED",
            title="Subscription updated",
            message=f"Subscription plan {subscription.subscription_name} was updated.",
            entity_type="subscription",
            entity_id=str(subscription.subscription_id),
            target_route=f"/super-admin/subscriptions/{subscription.subscription_id}",
            metadata={
                "updated_fields": sorted(update_data.keys()),
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
            event_key=f"subscription_updated:{subscription.subscription_id}:{subscription.updated_at}",
            commit=True,
        )

        return await SubscriptionService._response(session, subscription)

    @staticmethod
    async def set_default(
        session,
        subscription_id: UUID,
        actor=None,
    ):
        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        if not subscription.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive subscription plans cannot be default.",
            )

        await SubscriptionRepository.clear_default_for_type(
            session=session,
            subscription_type=subscription.subscription_type,
            exclude_subscription_id=subscription.subscription_id,
        )
        subscription.is_default = True
        await SubscriptionService._sync_default_setting(session, subscription)
        subscription = await SubscriptionRepository.update(
            session=session,
            subscription=subscription,
        )
        await SubscriptionService._log_plan_activity(
            session,
            actor=actor,
            action="SUBSCRIPTION_UPDATED",
            subscription=subscription,
            description=f"Subscription plan {subscription.subscription_name} set as default",
            metadata={
                "change": "SET_DEFAULT",
                "subscription_type": subscription.subscription_type,
            },
        )

        return await SubscriptionService._response(session, subscription)

    @staticmethod
    async def delete(
        session,
        subscription_id: UUID,
        actor=None,
    ):

        subscription = await SubscriptionRepository.get_by_id(
            session=session,
            subscription_id=subscription_id,
        )

        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found.",
            )

        settings = await SystemSettingsRepository.get_active(session)
        configured_defaults = {
            getattr(settings, "candidate_default_subscription_plan", None),
            getattr(settings, "employer_default_subscription_plan", None),
            getattr(settings, "default_subscription_plan", None),
        }
        if subscription.is_default or str(subscription.subscription_id) in configured_defaults:
            raise HTTPException(
                status_code=400,
                detail="Default subscription plans cannot be deleted. Set another default plan first.",
            )

        assignment_count = await SubscriptionRepository.count_user_assignments(
            session=session,
            subscription_id=subscription.subscription_id,
        )
        if assignment_count:
            raise HTTPException(
                status_code=400,
                detail="Subscription plans assigned to users cannot be deleted. Deactivate the plan instead.",
            )

        await SubscriptionRepository.delete(
            session=session,
            subscription=subscription,
        )
        await SubscriptionService._log_plan_activity(
            session,
            actor=actor,
            action="SUBSCRIPTION_DELETED",
            subscription=subscription,
            description=f"Subscription plan {subscription.subscription_name} deleted",
            metadata={
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
        )
        await NotificationService.create_for_super_admins(
            session,
            notification_type="SUBSCRIPTION_DELETED",
            title="Subscription deleted",
            message=f"Subscription plan {subscription.subscription_name} was deleted.",
            entity_type="subscription",
            entity_id=str(subscription.subscription_id),
            target_route="/super-admin/subscriptions",
            metadata={
                "subscription_type": subscription.subscription_type,
                "is_default": subscription.is_default,
                "is_active": subscription.is_active,
            },
            event_key=f"subscription_deleted:{subscription.subscription_id}",
            commit=True,
        )

        return {
            "message": "Subscription deleted successfully."
        }
