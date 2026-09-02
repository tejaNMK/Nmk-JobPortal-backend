from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.schema.notification import (
    NotificationListResponseSchema,
    NotificationSuccessResponseSchema,
)
from app.service.notification_service import NotificationService

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


@router.get(
    "",
    response_model=NotificationListResponseSchema,
)
async def get_notifications(
    payload: dict = Depends(get_jwt_payload_401),
    session=Depends(get_db),
):
    """
    Returns all notifications for the logged-in user.
    """

    recipient_id = payload.get("user_id")

    notifications = await NotificationService.get_notifications(
        session=session,
        recipient_id=str(recipient_id),
    )

    return NotificationListResponseSchema(
        notifications=notifications,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationSuccessResponseSchema,
)
async def mark_notification_as_read(
    notification_id: str,
    payload: dict = Depends(get_jwt_payload_401),
    session=Depends(get_db),
):
    """
    Marks a single notification as read.
    """

    recipient_id = payload.get("user_id")

    updated = await NotificationService.mark_as_read(
        session=session,
        notification_id=notification_id,
        recipient_id=str(recipient_id),
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Notification not found.",
        )

    return NotificationSuccessResponseSchema(
        success=True,
        message="Notification marked as read.",
    )


@router.patch(
    "/read-all",
    response_model=NotificationSuccessResponseSchema,
)
async def mark_all_notifications_as_read(
    payload: dict = Depends(get_jwt_payload_401),
    session=Depends(get_db),
):
    """
    Marks all notifications as read.
    """

    recipient_id = payload.get("user_id")

    count = await NotificationService.mark_all_as_read(
        session=session,
        recipient_id=str(recipient_id),
    )

    return NotificationSuccessResponseSchema(
        success=True,
        message=f"{count} notification(s) marked as read.",
    )