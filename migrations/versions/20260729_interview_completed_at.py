"""add interview completed timestamp

Revision ID: 20260729_interview_completed_at
Revises: 20260729_job_alert_deliveries
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_interview_completed_at"
down_revision = "20260729_job_alert_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "completed_at")
