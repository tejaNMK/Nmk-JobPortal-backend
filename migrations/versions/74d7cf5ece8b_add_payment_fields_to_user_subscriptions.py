"""add payment fields to user subscriptions

Revision ID: 74d7cf5ece8b
Revises: db1ce015b7d7
Create Date: 2026-07-22 18:07:56.505610
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "74d7cf5ece8b"
down_revision = "db1ce015b7d7"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "price_paid",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "discount_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "currency",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'INR'"),
        ),
    )

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "transaction_reference",
            sa.String(255),
            nullable=True,
        ),
    )

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "invoice_number",
            sa.String(100),
            nullable=True,
        ),
    )

    op.add_column(
        "user_subscriptions",
        sa.Column(
            "remarks",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:

    op.drop_column(
        "user_subscriptions",
        "remarks",
    )

    op.drop_column(
        "user_subscriptions",
        "invoice_number",
    )

    op.drop_column(
        "user_subscriptions",
        "transaction_reference",
    )

    op.drop_column(
        "user_subscriptions",
        "currency",
    )

    op.drop_column(
        "user_subscriptions",
        "discount_amount",
    )

    op.drop_column(
        "user_subscriptions",
        "price_paid",
    )