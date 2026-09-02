from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.schema.common import ResponseSchema, success_response
from app.schema.notification import (
    NotificationDeletedCountData,
    NotificationUpdatedCountData,
    PaginationSchema,
    SuperAdminNotificationListData,
    SuperAdminUnreadCountData,
)
from app.service.notification_service import NotificationService
from app.utils.date_range import normalize_date_range


router = APIRouter(
    prefix="/super-admin/notifications",
    tags=["Super Admin Notifications"],
    dependencies=[Depends(super_admin_only)],
)


@router.get("", response_model=ResponseSchema)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    is_read: bool | None = Query(default=None),
    notification_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    recipient_id = str(payload.get("user_id"))
    date_range = normalize_date_range(
        from_date=from_date,
        to_date=to_date,
        timezone_name=timezone,
    )
    total = await NotificationService.count_notifications(
        session=session,
        recipient_id=recipient_id,
        is_read=is_read,
        notification_type=notification_type,
        date_range=date_range,
        search=search,
    )
    items = await NotificationService.get_notifications(
        session=session,
        recipient_id=recipient_id,
        page=page,
        page_size=page_size,
        is_read=is_read,
        notification_type=notification_type,
        date_range=date_range,
        search=search,
        sort_order=sort_order,
    )
    unread_count = await NotificationService.get_unread_count(
        session=session,
        recipient_id=recipient_id,
    )
    data = SuperAdminNotificationListData(
        items=items,
        pagination=PaginationSchema(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=ceil(total / page_size) if total else 0,
        ),
        unread_count=unread_count,
        range=date_range.as_response(),
    )
    return success_response(
        data=data.model_dump(),
        message="Notifications fetched successfully.",
    )


@router.get("/unread-count", response_model=ResponseSchema)
async def unread_count(
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    count = await NotificationService.get_unread_count(
        session=session,
        recipient_id=str(payload.get("user_id")),
    )
    return success_response(
        data=SuperAdminUnreadCountData(unread_count=count).model_dump(),
        message="Unread notification count fetched successfully.",
    )


@router.patch("/read-all", response_model=ResponseSchema)
async def mark_all_read(
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    updated = await NotificationService.mark_all_as_read(
        session=session,
        recipient_id=str(payload.get("user_id")),
    )
    return success_response(
        data=NotificationUpdatedCountData(updated_count=updated).model_dump(),
        message="Notifications marked as read successfully.",
    )


@router.delete("/clear-read", response_model=ResponseSchema)
async def clear_read(
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    deleted = await NotificationService.clear_read_for_user(
        session=session,
        recipient_id=str(payload.get("user_id")),
    )
    return success_response(
        data=NotificationDeletedCountData(deleted_count=deleted).model_dump(),
        message="Read notifications cleared successfully.",
    )


@router.patch("/{notification_id}/read", response_model=ResponseSchema)
async def mark_read(
    notification_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    updated = await NotificationService.mark_as_read(
        session=session,
        notification_id=notification_id,
        recipient_id=str(payload.get("user_id")),
    )
    return success_response(
        data={"updated": updated},
        message="Notification marked as read successfully.",
    )


@router.delete("/{notification_id}", response_model=ResponseSchema)
async def delete_notification(
    notification_id: str,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    deleted = await NotificationService.delete_notification(
        session=session,
        notification_id=notification_id,
        recipient_id=str(payload.get("user_id")),
    )
    return success_response(
        data={"deleted": deleted},
        message="Notification deleted successfully.",
    )
