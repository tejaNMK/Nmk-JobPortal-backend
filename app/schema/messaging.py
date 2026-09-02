from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


MessageSortBy = Literal["RECENT", "OLDEST"]


class ConversationParticipant(BaseModel):
    """The 'other side' of a candidate's conversation."""

    kind: Literal["EMPLOYER", "SYSTEM"] = "EMPLOYER"
    employer_user_id: Optional[str] = None
    name: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    company_logo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationListItem(BaseModel):
    thread_id: str
    subject: str
    participant: ConversationParticipant
    last_message_preview: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_message_is_mine: bool = False
    unread_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    items: List[ConversationListItem]
    total: int
    page: int
    page_size: int
    total_unread: int

    model_config = ConfigDict(from_attributes=True)


class MessageItem(BaseModel):
    message_id: str
    thread_id: str
    from_me: bool
    is_system: bool = False
    sender_name: Optional[str] = None
    body: str
    sent_at: datetime
    read: bool

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    thread_id: str
    subject: str
    participant: ConversationParticipant
    messages: List[MessageItem]

    model_config = ConfigDict(from_attributes=True)


class SendReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class SendReplyResponse(BaseModel):
    message: MessageItem

    model_config = ConfigDict(from_attributes=True)


class ComposeMessageRequest(BaseModel):
    company_id: str
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=5000)
    job_id: Optional[str] = None


class ComposeMessageResponse(BaseModel):
    thread_id: str
    message: MessageItem

    model_config = ConfigDict(from_attributes=True)


class MessageableCompany(BaseModel):
    company_id: str
    company_name: str
    company_logo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MessageableCompaniesResponse(BaseModel):
    items: List[MessageableCompany]

    model_config = ConfigDict(from_attributes=True)


class MarkReadResponse(BaseModel):
    thread_id: Optional[str] = None
    marked_read: int

    model_config = ConfigDict(from_attributes=True)