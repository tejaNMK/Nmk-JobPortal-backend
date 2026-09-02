"""subscription defaults

Revision ID: 20260727_subscription_defaults
Revises: 20260727_job_alert_title
Create Date: 2026-07-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260727_subscription_defaults"
down_revision = "20260727_remove_extra_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "uq_subscriptions_default_by_type",
        "subscriptions",
        ["subscription_type"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    op.create_index(
        "idx_user_subscriptions_role_status",
        "user_subscriptions",
        ["role", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_user_subscriptions_role_status",
        table_name="user_subscriptions",
    )
    op.drop_index(
        "uq_subscriptions_default_by_type",
        table_name="subscriptions",
    )
    op.drop_column("subscriptions", "is_default")
