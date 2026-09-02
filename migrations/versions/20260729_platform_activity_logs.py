"""extend activity logs for platform audit trail

Revision ID: 20260729_platform_activity_logs
Revises: 20260729_subscription_integrity
Create Date: 2026-07-29 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260729_platform_activity_logs"
down_revision = "20260729_subscription_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_logs",
        sa.Column("target_entity_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "activity_logs",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "idx_activity_logs_actor_role",
        "activity_logs",
        ["actor_role"],
    )
    op.create_index(
        "idx_activity_logs_entity_type",
        "activity_logs",
        ["entity_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_activity_logs_entity_type", table_name="activity_logs")
    op.drop_index("idx_activity_logs_actor_role", table_name="activity_logs")
    op.drop_column("activity_logs", "metadata")
    op.drop_column("activity_logs", "target_entity_name")
