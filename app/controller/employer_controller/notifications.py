from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema, success_response
from app.schema.notification import NotificationBulkActionRequest
from app.service.employer_service.notification_service import (
    EmployerNotificationService,
)


router = APIRouter(
    prefix="/employer/notifications",
    tags=["Employer Notifications"],
    dependencies=[Depends(employer_user_only)],
)


@router.get("", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    is_read: bool | None = Query(default=None),
    notification_type: str | None = Query(default=None),
    filter: str | None = Query(default=None),
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.list_notifications(
        session=session,
        payload=payload,
        page=page,
        page_size=page_size,
        is_read=is_read,
        notification_type=notification_type,
        filter=filter,
        category=category,
        priority=priority,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
        search=search,
        sort_order=sort_order,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notifications fetched successfully.",
    )


@router.get(
    "/unread-count",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def unread_count(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.unread_count(
        session=session,
        payload=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="Unread employer notification count fetched successfully.",
    )


@router.patch(
    "/read-all",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def mark_all_read(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.mark_all_as_read(
        session=session,
        payload=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notifications marked as read successfully.",
    )


@router.delete(
    "/clear-read",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def clear_read_notifications(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.clear_read_notifications(
        session=session,
        payload=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="Read employer notifications deleted successfully.",
    )


@router.patch(
    "/batch/read",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def mark_many_read(
    request: NotificationBulkActionRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.mark_many_as_read(
        session=session,
        payload=payload,
        notification_ids=request.notification_ids,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notifications marked as read successfully.",
    )


@router.delete(
    "/batch",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def delete_many_notifications(
    request: NotificationBulkActionRequest,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.delete_many(
        session=session,
        payload=payload,
        notification_ids=request.notification_ids,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notifications deleted successfully.",
    )


@router.patch(
    "/{notification_id}/read",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def mark_read(
    notification_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.mark_as_read(
        session=session,
        payload=payload,
        notification_id=notification_id,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notification marked as read successfully.",
    )


@router.delete(
    "/{notification_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def delete_notification(
    notification_id: str,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerNotificationService.delete_notification(
        session=session,
        payload=payload,
        notification_id=notification_id,
    )
    return success_response(
        data=data.model_dump(),
        message="Employer notification deleted successfully.",
    )
