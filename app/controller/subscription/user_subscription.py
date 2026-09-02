from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import (
    ResponseSchema,
    created_response,
    success_response,
)
from app.schema.subscription.user_subscription import (
    AssignSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeSubscriptionRequest,
    RenewSubscriptionRequest,
    SelfSubscribeRequest,
    SubscriptionActionRequest,
    UsageResetRequest,
)
from app.service.subscription.user_subscription_service import (
    UserSubscriptionService,
)
from app.service.subscription.subscription_service import SubscriptionService
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import super_admin_only

router = APIRouter(
    prefix="/super-admin/user-subscriptions",
    tags=["Super Admin User Subscriptions"],
    dependencies=[Depends(super_admin_only)],
)


# =====================================================
# Assign Subscription
# =====================================================

@router.post(
    "",
    response_model=ResponseSchema,
    status_code=201,
)
async def assign_subscription(
    request: AssignSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.assign_subscription(
        session=session,
        request=request,
        assigned_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )

    return created_response(
        data=data.model_dump(),
        message="Subscription assigned successfully.",
    )


@router.post(
    "/default",
    response_model=ResponseSchema,
    status_code=201,
)
async def assign_default_subscription(
    request: AssignSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.assign_default_subscription(
        session=session,
        user_id=request.user_id,
        role=request.role,
        assigned_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
        remarks=request.remarks,
    )

    return created_response(
        data=data.model_dump(),
        message="Default subscription assigned successfully.",
    )


# =====================================================
# Get Active Subscription
# =====================================================

@router.get(
    "/subscribers/active",
    response_model=ResponseSchema,
)
async def list_active_subscribers(
    role: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.list_subscribers(
        session=session,
        active=True,
        role=role,
    )
    return success_response(
        data=[item.model_dump() for item in data],
        message="Active subscribers fetched successfully.",
    )


@router.get(
    "/subscribers/inactive",
    response_model=ResponseSchema,
)
async def list_inactive_subscribers(
    role: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.list_subscribers(
        session=session,
        active=False,
        role=role,
    )
    return success_response(
        data=[item.model_dump() for item in data],
        message="Inactive subscribers fetched successfully.",
    )


# =====================================================
# Subscription History
# =====================================================

@router.get(
    "/users/{user_id}/history",
    response_model=ResponseSchema,
)
async def get_subscription_history_by_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.get_history(
        session=session,
        user_id=user_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription history fetched successfully",
    )


@router.get(
    "/{user_subscription_id}/details",
    response_model=ResponseSchema,
)
async def get_subscription_details_canonical(
    user_subscription_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.get_details(
        session=session,
        user_subscription_id=user_subscription_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription details fetched successfully",
    )


# =====================================================
# Subscription Details
# =====================================================

@router.get(
    "/details/{user_subscription_id}",
    response_model=ResponseSchema,
    deprecated=True,
)
async def get_subscription_details(
    user_subscription_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.get_details(
        session=session,
        user_subscription_id=user_subscription_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription details fetched successfully",
    )


@router.get(
    "/{user_id}",
    response_model=ResponseSchema,
)
async def get_active_subscription(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.get_active_subscription(
        session=session,
        user_id=user_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Active subscription fetched successfully.",
    )


# =====================================================
# Subscription History
# =====================================================

@router.get(
    "/{user_id}/history",
    response_model=ResponseSchema,
    deprecated=True,
)
async def get_subscription_history(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await UserSubscriptionService.get_history(
        session=session,
        user_id=user_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription history fetched successfully",
    )


@router.get(
    "/{user_subscription_id}/usage",
    response_model=ResponseSchema,
)
async def get_subscription_usage(
    user_subscription_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )
    data = await UserSubscriptionService.get_remaining_usage(
        session=session,
        user_id=current.user_id,
        user_subscription_id=user_subscription_id,
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription usage fetched successfully.",
    )


@router.post(
    "/{user_subscription_id}/usage/reset",
    response_model=ResponseSchema,
)
async def reset_subscription_usage(
    user_subscription_id: UUID,
    request: UsageResetRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )
    data = await UserSubscriptionService.reset_usage(
        session=session,
        user_id=current.user_id,
        request=request,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
        user_subscription_id=user_subscription_id,
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription usage reset successfully.",
    )


# =====================================================
# Renew Subscription
# =====================================================

@router.patch(
    "/{user_subscription_id}/renew",
    response_model=ResponseSchema,
)
async def renew_subscription(
    user_subscription_id: UUID,
    request: RenewSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )

    data = await UserSubscriptionService.renew_subscription(
        session=session,
        user_id=current.user_id,
        request=request,
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription renewed successfully.",
    )


@router.patch(
    "/{user_subscription_id}/upgrade",
    response_model=ResponseSchema,
)
async def upgrade_subscription(
    user_subscription_id: UUID,
    request: ChangeSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=current.user_id,
        request=request,
        action="UPGRADED",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription upgraded successfully.")


@router.patch(
    "/{user_subscription_id}/change-plan",
    response_model=ResponseSchema,
)
async def change_subscription_plan(
    user_subscription_id: UUID,
    request: ChangeSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=current.user_id,
        request=request,
        action="CHANGE_PLAN",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription plan changed successfully.")


@router.patch(
    "/{user_subscription_id}/downgrade",
    response_model=ResponseSchema,
)
async def downgrade_subscription(
    user_subscription_id: UUID,
    request: ChangeSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=current.user_id,
        request=request,
        action="DOWNGRADED",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription downgraded successfully.")


@router.patch(
    "/{user_subscription_id}/suspend",
    response_model=ResponseSchema,
)
async def suspend_subscription(
    user_subscription_id: UUID,
    request: SubscriptionActionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(session=session, user_subscription_id=user_subscription_id)
    data = await UserSubscriptionService.update_status(
        session=session,
        user_id=current.user_id,
        request=request,
        status="SUSPENDED",
        action="SUSPENDED",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription suspended successfully.")


@router.patch(
    "/{user_subscription_id}/resume",
    response_model=ResponseSchema,
)
async def resume_subscription(
    user_subscription_id: UUID,
    request: SubscriptionActionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(session=session, user_subscription_id=user_subscription_id)
    data = await UserSubscriptionService.update_status(
        session=session,
        user_id=current.user_id,
        request=request,
        status="ACTIVE",
        action="RESUMED",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription resumed successfully.")


@router.patch(
    "/{user_subscription_id}/expire",
    response_model=ResponseSchema,
)
async def expire_subscription(
    user_subscription_id: UUID,
    request: SubscriptionActionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    current = await UserSubscriptionService.get_by_id(session=session, user_subscription_id=user_subscription_id)
    data = await UserSubscriptionService.update_status(
        session=session,
        user_id=current.user_id,
        request=request,
        status="EXPIRED",
        action="EXPIRED",
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )
    return success_response(data=data.model_dump(), message="Subscription expired successfully.")


# =====================================================
# Cancel Subscription
# =====================================================

@router.patch(
    "/{user_subscription_id}/cancel",
    response_model=ResponseSchema,
)
async def cancel_subscription(
    user_subscription_id: UUID,
    request: CancelSubscriptionRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    current = await UserSubscriptionService.get_by_id(
        session=session,
        user_subscription_id=user_subscription_id,
    )

    data = await UserSubscriptionService.cancel_subscription(
        session=session,
        user_id=current.user_id,
        request=request,
        user_subscription_id=user_subscription_id,
        performed_by=UUID(str(payload.get("user_id"))) if payload.get("user_id") else None,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription cancelled successfully.",
    )


self_router = APIRouter(
    prefix="/user/subscription",
    tags=["User Subscriptions"],
)


def _payload_user_id(payload) -> UUID:
    return UUID(str(payload.get("user_id")))


@self_router.get(
    "/plans",
    response_model=ResponseSchema,
)
async def list_my_available_subscription_plans(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await SubscriptionService.get_available_for_user(
        session=session,
        user_id=_payload_user_id(payload),
    )
    return success_response(
        data=[subscription.model_dump() for subscription in data],
        message="Available subscription plans fetched successfully.",
    )


@self_router.get(
    "",
    response_model=ResponseSchema,
)
async def get_my_subscription(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.get_current_subscription(
        session=session,
        user_id=_payload_user_id(payload),
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription fetched successfully.",
    )


@self_router.post(
    "",
    response_model=ResponseSchema,
    status_code=201,
)
async def subscribe_to_plan(
    request: SelfSubscribeRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.subscribe_self(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
    )
    return created_response(
        data=data.model_dump(),
        message="Subscription created successfully.",
    )


@self_router.post(
    "/renew",
    response_model=ResponseSchema,
)
async def renew_my_subscription(
    request: RenewSubscriptionRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.renew_subscription(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
        performed_by=_payload_user_id(payload),
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription renewed successfully.",
    )


@self_router.post(
    "/upgrade",
    response_model=ResponseSchema,
)
async def upgrade_my_subscription(
    request: ChangeSubscriptionRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
        action="UPGRADED",
        performed_by=_payload_user_id(payload),
    )
    return success_response(data=data.model_dump(), message="Subscription upgraded successfully.")


@self_router.post(
    "/change-plan",
    response_model=ResponseSchema,
)
async def change_my_subscription_plan(
    request: ChangeSubscriptionRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
        action="CHANGE_PLAN",
        performed_by=_payload_user_id(payload),
    )
    return success_response(data=data.model_dump(), message="Subscription plan changed successfully.")


@self_router.post(
    "/downgrade",
    response_model=ResponseSchema,
)
async def downgrade_my_subscription(
    request: ChangeSubscriptionRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.change_subscription(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
        action="DOWNGRADED",
        performed_by=_payload_user_id(payload),
    )
    return success_response(data=data.model_dump(), message="Subscription downgraded successfully.")


@self_router.post(
    "/cancel",
    response_model=ResponseSchema,
)
async def cancel_my_subscription(
    request: CancelSubscriptionRequest,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.cancel_subscription(
        session=session,
        user_id=_payload_user_id(payload),
        request=request,
        performed_by=_payload_user_id(payload),
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription cancelled successfully.",
    )


@self_router.get(
    "/history",
    response_model=ResponseSchema,
)
async def get_my_subscription_history(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.get_history(
        session=session,
        user_id=_payload_user_id(payload),
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription history fetched successfully",
    )


@self_router.get(
    "/usage",
    response_model=ResponseSchema,
)
async def get_my_subscription_usage(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await UserSubscriptionService.get_remaining_usage(
        session=session,
        user_id=_payload_user_id(payload),
    )
    return success_response(
        data=data.model_dump(),
        message="Subscription usage fetched successfully.",
    )


