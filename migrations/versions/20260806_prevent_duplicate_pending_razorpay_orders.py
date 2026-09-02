"""prevent duplicate pending razorpay orders

Revision ID: 20260806_prevent_duplicate_pending_razorpay_orders
Revises: 20260805_razorpay_fields
Create Date: 2026-08-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_prevent_duplicate_pending_razorpay_orders"
down_revision = "20260805_razorpay_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_user_pending_razorpay_subscription",
        "user_subscriptions",
        ["user_id", "role"],
        unique=True,
        postgresql_where=sa.text(
            "payment_gateway = 'RAZORPAY' "
            "AND status = 'PENDING' "
            "AND payment_status = 'PENDING'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_user_pending_razorpay_subscription",
        table_name="user_subscriptions",
    )
