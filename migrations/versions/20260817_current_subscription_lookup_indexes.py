"""add current subscription lookup indexes

Revision ID: 20260817_current_subscription_lookup_indexes
Revises: 20260817_status_history_reason
Create Date: 2026-08-17
"""

from alembic import op


revision = "20260817_current_subscription_lookup_indexes"
down_revision = "20260817_status_history_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_user_subscriptions_subscription_id",
        "user_subscriptions",
        ["subscription_id"],
    )
    op.create_index(
        "idx_user_subscriptions_status",
        "user_subscriptions",
        ["status"],
    )
    op.create_index(
        "idx_user_subscriptions_current_lookup",
        "user_subscriptions",
        ["user_id", "status", "start_date", "end_date", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_user_subscriptions_current_lookup",
        table_name="user_subscriptions",
    )
    op.drop_index(
        "idx_user_subscriptions_status",
        table_name="user_subscriptions",
    )
    op.drop_index(
        "idx_user_subscriptions_subscription_id",
        table_name="user_subscriptions",
    )
