from datetime import datetime
from app.utils.utc import utc_now_naive
from sqlmodel import Field


class TimeMixin:

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        nullable=False
    )

    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        nullable=False
    )
