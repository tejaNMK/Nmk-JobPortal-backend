from datetime import datetime
from typing import List, Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class MessageThread(SQLModel, table=True):
    __tablename__ = "message_threads"

    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    subject: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))

    messages: List["Message"] = Relationship(back_populates="thread")
