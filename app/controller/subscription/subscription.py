from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import (
    ResponseSchema,
    created_response,
    success_response,
)
from app.schema.subscription.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from app.service.subscription.subscription_service import (
    SubscriptionService,
)
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import super_admin_only

router = APIRouter(
    prefix="/super-admin/subscriptions",
    tags=["Subscriptions"],
    dependencies=[Depends(super_admin_only)],
)

catalogue_router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"],
)


@router.post(
    "",
    response_model=ResponseSchema[SubscriptionResponse],
    status_code=201,
)
async def create_subscription(
    request: SubscriptionCreate,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.create(
        session=session,
        request=request,
        actor=payload,
    )

    return created_response(
        data=data.model_dump(),
        message="Subscription created successfully.",
    )


@router.get(
    "",
    response_model=ResponseSchema[list[SubscriptionResponse]],
)
async def list_subscriptions(
    subscription_type: str | None = None,
    status: str | None = None,
    billing_cycle: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.get_all(
        session=session,
        subscription_type=subscription_type,
        status=status,
        billing_cycle=billing_cycle,
        search=search,
    )

    return success_response(
        data=[subscription.model_dump() for subscription in data],
        message="Subscriptions fetched successfully.",
    )


@catalogue_router.get(
    "/plans",
    response_model=ResponseSchema,
)
async def list_subscription_plan_catalogue(
    subscription_type: str | None = None,
    status: str | None = None,
    billing_cycle: str | None = None,
    search: str | None = None,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    data = await SubscriptionService.get_catalogue_for_payload(
        session=session,
        payload=payload,
        subscription_type=subscription_type,
        status=status,
        billing_cycle=billing_cycle,
        search=search,
    )

    return success_response(
        data=[subscription.model_dump() for subscription in data],
        message="Subscription plans fetched successfully.",
    )


@router.get(
    "/{subscription_id}",
    response_model=ResponseSchema[SubscriptionResponse],
)
async def get_subscription(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.get_by_id(
        session=session,
        subscription_id=subscription_id,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription fetched successfully.",
    )


@router.patch(
    "/{subscription_id}/default",
    response_model=ResponseSchema[SubscriptionResponse],
)
async def set_default_subscription(
    subscription_id: UUID,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.set_default(
        session=session,
        subscription_id=subscription_id,
        actor=payload,
    )

    return success_response(
        data=data.model_dump(),
        message="Default subscription updated successfully.",
    )


@router.put(
    "/{subscription_id}",
    response_model=ResponseSchema[SubscriptionResponse],
)
async def update_subscription(
    subscription_id: UUID,
    request: SubscriptionUpdate,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.update(
        session=session,
        subscription_id=subscription_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription updated successfully.",
    )


@router.patch(
    "/{subscription_id}",
    response_model=ResponseSchema[SubscriptionResponse],
)
async def patch_subscription(
    subscription_id: UUID,
    request: SubscriptionUpdate,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.update(
        session=session,
        subscription_id=subscription_id,
        request=request,
        actor=payload,
    )

    return success_response(
        data=data.model_dump(),
        message="Subscription updated successfully.",
    )


@router.delete(
    "/{subscription_id}",
    response_model=ResponseSchema,
)
async def delete_subscription(
    subscription_id: UUID,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):

    data = await SubscriptionService.delete(
        session=session,
        subscription_id=subscription_id,
        actor=payload,
    )

    return success_response(
        data=data,
        message="Subscription deleted successfully.",
    )
