import uuid
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, text
from sqlmodel import Field, SQLModel


class CandidateTargetRole(SQLModel, table=True):
    """Many-to-many link between a candidate profile and their selected
    target roles (multi-select with search/autocomplete)."""
    __tablename__ = "candidate_target_roles"
    __table_args__ = (
        Index("idx_candidate_target_roles_candidate", "candidate_id"),
        Index("idx_candidate_target_roles_unique", "candidate_id", "target_role_id", unique=True),
    )

    candidate_target_role_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")),
    )
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    target_role_id: str = Field(sa_column=Column(Text, ForeignKey("master_target_roles.target_role_id"), nullable=False))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
