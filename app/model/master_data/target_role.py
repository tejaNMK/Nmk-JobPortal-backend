import uuid
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, SQLModel


class MasterTargetRole(SQLModel, table=True):
    """Reference list of role titles, used to power the Target Roles
    multi-select with search/autocomplete. Candidates may also add a role
    that isn't yet in the list; it gets created here on the fly so it
    becomes searchable for everyone afterwards.
    """
    __tablename__ = "master_target_roles"
    __table_args__ = (Index("idx_master_target_roles_name", "name", unique=True),)

    target_role_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")),
    )
    name: str = Field(sa_column=Column(String(150), nullable=False))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
