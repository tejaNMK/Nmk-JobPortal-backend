from datetime import datetime
from typing import Optional
from uuid import UUID

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel


class ApplicationStatusHistory(SQLModel, table=True):
    __tablename__ = "application_status_history"

    history_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    application_id: str = Field(sa_column=Column(Text, ForeignKey("job_applications.application_id"), nullable=False))
    old_status: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    new_status: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    changed_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    changed_by: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id")))

    application: "JobApplication" = Relationship(back_populates="status_history")
    changed_by_user: Optional["Users"] = Relationship(back_populates="application_status_changes")
