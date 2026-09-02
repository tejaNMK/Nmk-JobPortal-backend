from datetime import datetime
from typing import Optional
from uuid import UUID

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    thread_id: str = Field(sa_column=Column(Text, ForeignKey("message_threads.thread_id"), nullable=False))
    sender_id: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id")))
    receiver_id: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id")))
    message_body: Optional[str] = Field(default=None, sa_column=Column(Text))
    sent_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    read_flag: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))

    thread: "MessageThread" = Relationship(back_populates="messages")
    sender: Optional["Users"] = Relationship(back_populates="sent_messages", sa_relationship_kwargs={"foreign_keys": "Message.sender_id"})
    receiver: Optional["Users"] = Relationship(back_populates="received_messages", sa_relationship_kwargs={"foreign_keys": "Message.receiver_id"})
