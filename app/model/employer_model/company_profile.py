from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing


class CompanyProfile(SQLModel, table=True):
    __tablename__ = "company_profiles"
    __table_args__ = (
        Index("idx_company_name", "company_name"),
        Index("idx_company_profiles_public", "is_public"),
        Index("idx_company_profiles_industry", "industry"),
        Index("idx_company_profiles_verification", "verification_status"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )
    company_id: str = Field(
        default_factory=lambda: uuid4().hex,
        sa_column=Column(
            Text,
            nullable=False,
            unique=True,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )
    employer_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("employer_profiles.id"),
            nullable=False,
            unique=True,
        )
    )
    company_name: str = Field(sa_column=Column(String(150), nullable=False))
    website: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    logo_path: Optional[str] = Field(default=None, sa_column=Column(Text))
    logo_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(String(2000)))
    industry: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    size: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    company_size: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    founded_year: Optional[int] = Field(default=None, sa_column=Column(Integer))
    location: Optional[str] = Field(default=None, sa_column=Column(Text))
    headquarters_country: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    headquarters_state: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    headquarters_city: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    contact_email: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    contact_phone: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    verification_status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False, server_default=text("'PENDING'")),
    )
    verified_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    approved_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    rejected_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    rejection_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_public: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_by: Optional[str] = Field(default=None, sa_column=Column(Text))

    followers: List["CandidateCompanyFollowing"] = Relationship(
        back_populates="company"
    )
