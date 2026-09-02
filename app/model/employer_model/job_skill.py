from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.model.employer_model.job import Job


class JobSkill(SQLModel, table=True):
    """Normalized job skills — one row per skill per job."""

    __tablename__ = "job_skills"

    job_id: str = Field(
        sa_column=Column(Text, ForeignKey("jobs.job_id"), primary_key=True),
    )

    skill: str = Field(sa_column=Column(Text, primary_key=True))

    # Relationship back to Job
    job: "Job" = Relationship(back_populates="skills")

