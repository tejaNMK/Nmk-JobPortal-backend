"""add structured job location fields

Revision ID: 20260729_job_structured_location
Revises: 20260729_job_detail_fields
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_job_structured_location"
down_revision = "20260729_job_detail_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("country_id", sa.Text(), sa.ForeignKey("master_countries.country_id"), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("location_id", sa.Text(), sa.ForeignKey("master_locations.location_id"), nullable=True),
    )
    op.add_column("jobs", sa.Column("custom_city", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "custom_city")
    op.drop_column("jobs", "location_id")
    op.drop_column("jobs", "country_id")
