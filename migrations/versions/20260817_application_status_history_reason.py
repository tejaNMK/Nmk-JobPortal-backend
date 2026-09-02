"""add reason to application status history

Revision ID: 20260817_status_history_reason
Revises: 20260817_merge_payment_ai_timestamps
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260817_status_history_reason"
down_revision = "20260817_merge_payment_ai_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_status_history",
        sa.Column("reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_status_history", "reason")
