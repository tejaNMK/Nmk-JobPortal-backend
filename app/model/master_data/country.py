import uuid
from datetime import datetime
from typing import List, Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class MasterCountry(SQLModel, table=True):
    __tablename__ = "master_countries"
    __table_args__ = (Index("idx_master_countries_name", "name", unique=True),)

    country_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")),
    )
    name: str = Field(sa_column=Column(String(150), nullable=False))
    iso_code: Optional[str] = Field(default=None, sa_column=Column(String(3)))
    phone_code: Optional[str] = Field(default=None, sa_column=Column(String(10)))
    # ISO-4217 currency code (e.g. "USD", "INR", "EUR"), backfilled from
    # CLDR territory-currency data -- drives currency-aware UI like the
    # Current/Expected Salary field hints on Edit Profile.
    currency_code: Optional[str] = Field(default=None, sa_column=Column(String(3)))
    sort_order: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))

    locations: List["MasterLocation"] = Relationship(back_populates="country")