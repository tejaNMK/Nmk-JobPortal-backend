from datetime import datetime
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import BigInteger, Column, DateTime, String, Text, text
from sqlmodel import Field, SQLModel


class SearchKeyword(SQLModel, table=True):
    __tablename__ = "search_keywords"

    keyword_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    keyword: str = Field(sa_column=Column(String(255), nullable=False))
    suggestion_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    hit_count: int = Field(default=0, sa_column=Column(BigInteger, server_default=text("0")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
