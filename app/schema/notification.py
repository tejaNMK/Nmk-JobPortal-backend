from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponseSchema(BaseModel):
    notification_id: str
    type: str | None = None
    recipient_id: str
    recipient_user_id: str | None = None
    recipient_role: str | None = None
    title: str
    message: str
    description: str | None = None
    priority: str | None = None
    category: str | None = None
    icon: str | None = None
    color: str | None = None
    notification_type: str
    reference_type: str | None = None
    reference_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    target_route: str | None = None
    redirect_url: str | None = None
    relative_time: str | None = None
    action_required: bool = False
    action_button: str | None = None
    metadata: dict | None = Field(default=None, validation_alias="metadata_")
    event_key: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponseSchema(BaseModel):
    notifications: list[NotificationResponseSchema]


class MarkNotificationReadSchema(BaseModel):
    notification_id: str


class NotificationSuccessResponseSchema(BaseModel):
    success: bool
    message: str


class NotificationCountSchema(BaseModel):
    total_notifications: int
    unread_notifications: int
    today_notifications: int = 0
    high_priority_notifications: int = 0


class PaginationSchema(BaseModel):
    page: int
    page_size: int
    total: int | None = None
    total_items: int
    total_pages: int
    next_page: int | None = None
    previous_page: int | None = None


class SuperAdminNotificationListData(BaseModel):
    items: list[NotificationResponseSchema]
    pagination: PaginationSchema
    unread_count: int
    range: dict[str, str] | None = None


class SuperAdminUnreadCountData(BaseModel):
    unread_count: int


class EmployerNotificationListData(BaseModel):
    items: list[NotificationResponseSchema]
    pagination: PaginationSchema
    unread_count: int
    counts: NotificationCountSchema | None = None
    range: dict[str, str] | None = None


class EmployerUnreadCountData(BaseModel):
    total_notifications: int = 0
    unread_notifications: int = 0
    today_notifications: int = 0
    high_priority_notifications: int = 0
    unread_count: int


class NotificationBulkActionRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list, min_length=1)


class NotificationUpdatedCountData(BaseModel):
    updated_count: int


class NotificationDeletedCountData(BaseModel):
    deleted_count: int
