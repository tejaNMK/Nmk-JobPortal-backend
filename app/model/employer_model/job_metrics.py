from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, text
from sqlmodel import Field, SQLModel


class JobMetrics(SQLModel, table=True):
    __tablename__ = "job_metrics"

    metric_id: str = Field(sa_column=Column(Text, primary_key=True, nullable=False))
    job_id: str = Field(
        sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False)
    )
    view_count: Optional[int] = Field(
        default=0,
        sa_column=Column(Integer, server_default=text("0")),
    )
    application_count: Optional[int] = Field(
        default=0,
        sa_column=Column(Integer, server_default=text("0")),
    )
    shortlist_count: Optional[int] = Field(
        default=0,
        sa_column=Column(Integer, server_default=text("0")),
    )
    last_viewed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
