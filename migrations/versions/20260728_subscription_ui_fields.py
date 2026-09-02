"""subscription ui fields

Revision ID: 20260728_subscription_ui
Revises: 20260727_subscription_defaults
Create Date: 2026-07-28 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_subscription_ui"
down_revision = "20260728_follow_notify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "billing_cycle",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'Monthly'"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "is_popular",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "is_popular")
    op.drop_column("subscriptions", "display_order")
    op.drop_column("subscriptions", "billing_cycle")
