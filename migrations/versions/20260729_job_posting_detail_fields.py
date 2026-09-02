"""add job posting detail fields

Revision ID: 20260729_job_detail_fields
Revises: 20260729_default_sub_features
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_job_detail_fields"
down_revision = "20260729_default_sub_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("job_category", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("seniority_level", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("team_size", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("education", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("responsibilities", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("requirements", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("benefits", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("application_instructions", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("working_hours", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("office_location", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("map_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "map_url")
    op.drop_column("jobs", "office_location")
    op.drop_column("jobs", "working_hours")
    op.drop_column("jobs", "application_instructions")
    op.drop_column("jobs", "benefits")
    op.drop_column("jobs", "requirements")
    op.drop_column("jobs", "responsibilities")
    op.drop_column("jobs", "education")
    op.drop_column("jobs", "team_size")
    op.drop_column("jobs", "seniority_level")
    op.drop_column("jobs", "job_category")
