from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class AIJobDescriptionUsage(SQLModel, table=True):
    __tablename__ = "ai_job_description_usage"
    __table_args__ = (
        Index("idx_ai_job_description_usage_user_created", "employer_user_id", "created_at"),
        Index("idx_ai_job_description_usage_company_created", "company_id", "created_at"),
    )

    usage_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )
    employer_user_id: UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    )
    company_id: str = Field(
        sa_column=Column(Text, ForeignKey("employer_profiles.id"), nullable=False)
    )
    operation_type: str = Field(sa_column=Column(String(20), nullable=False))
    job_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("jobs.job_id")))
    ai_model: str = Field(sa_column=Column(String(100), nullable=False))
    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default=text("0")))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default=text("0")))
    request_status: str = Field(default="SUCCESS", sa_column=Column(String(20), nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
