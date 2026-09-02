"""add razorpay provider id uniqueness

Revision ID: 20260811_razorpay_provider_id_uniqueness
Revises: 20260806_prevent_duplicate_pending_razorpay_orders
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_razorpay_provider_id_uniqueness"
down_revision = "20260806_prevent_duplicate_pending_razorpay_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_user_subscriptions_razorpay_order_id",
        "user_subscriptions",
        ["razorpay_order_id"],
        unique=True,
        postgresql_where=sa.text("razorpay_order_id IS NOT NULL"),
    )
    op.create_index(
        "uq_user_subscriptions_razorpay_payment_id",
        "user_subscriptions",
        ["razorpay_payment_id"],
        unique=True,
        postgresql_where=sa.text("razorpay_payment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_subscriptions_razorpay_payment_id",
        table_name="user_subscriptions",
    )
    op.drop_index(
        "uq_user_subscriptions_razorpay_order_id",
        table_name="user_subscriptions",
    )
