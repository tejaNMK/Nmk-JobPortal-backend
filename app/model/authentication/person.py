from typing import Optional

from sqlmodel import SQLModel, Field

from app.model.authentication.mixins import TimeMixin


class Person(SQLModel, TimeMixin, table=True):
    __tablename__ = "person"

    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        nullable=False
    )

    name: str

    role: str