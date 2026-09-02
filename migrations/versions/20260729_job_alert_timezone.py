"""add job alert timezone

Revision ID: 20260729_job_alert_timezone
Revises: 20260729_job_alert_deliveries
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_job_alert_timezone"
down_revision = "20260729_job_alert_deliveries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_alerts",
        sa.Column("timezone", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_alerts", "timezone")
