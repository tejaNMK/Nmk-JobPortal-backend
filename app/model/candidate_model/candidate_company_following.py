from datetime import datetime
from typing import Optional, TYPE_CHECKING

import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Text, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.model.candidate_model.candidate_profile import CandidateProfile
    from app.model.employer_model.company_profile import CompanyProfile


class CandidateCompanyFollowing(SQLModel, table=True):
    """Tracks which companies a candidate is following."""

    __tablename__ = "candidate_company_followings"

    __table_args__ = (
        Index("idx_ccf_candidate_id", "candidate_id"),
        Index("idx_ccf_company_id", "company_id"),
    )

    following_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    candidate_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("candidate_profiles.candidate_id"),
            nullable=False,
        )
    )

    company_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("company_profiles.company_id"),
            nullable=False,
        )
    )

    followed_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    is_deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    candidate: Optional["CandidateProfile"] = Relationship(
        back_populates="company_followings"
    )

    company: Optional["CompanyProfile"] = Relationship(
        back_populates="followers"
    )