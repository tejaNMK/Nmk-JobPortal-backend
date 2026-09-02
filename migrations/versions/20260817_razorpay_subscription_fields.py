"""add razorpay subscription payment fields

Revision ID: 20260817_razorpay_subscription_fields
Revises: 74d7cf5ece8b
Create Date: 2026-08-17
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_razorpay_subscription_fields"
down_revision = "74d7cf5ece8b"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        column["name"]
        for column in inspector.get_columns("user_subscriptions")
    }


def _indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        index["name"]
        for index in inspector.get_indexes("user_subscriptions")
    }


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute(
            "ALTER TABLE user_subscriptions "
            "ADD COLUMN IF NOT EXISTS payment_gateway VARCHAR(50)"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(255)"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(255)"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "ADD COLUMN IF NOT EXISTS payment_verified_at TIMESTAMP"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_user_subscriptions_razorpay_order_id "
            "ON user_subscriptions (razorpay_order_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_user_subscriptions_razorpay_payment_id "
            "ON user_subscriptions (razorpay_payment_id)"
        )
        return

    columns = _columns()
    if "payment_gateway" not in columns:
        op.add_column(
            "user_subscriptions",
            sa.Column("payment_gateway", sa.String(length=50), nullable=True),
        )
    if "razorpay_order_id" not in columns:
        op.add_column(
            "user_subscriptions",
            sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
        )
    if "razorpay_payment_id" not in columns:
        op.add_column(
            "user_subscriptions",
            sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        )
    if "payment_verified_at" not in columns:
        op.add_column(
            "user_subscriptions",
            sa.Column("payment_verified_at", sa.DateTime(), nullable=True),
        )

    indexes = _indexes()
    if "ix_user_subscriptions_razorpay_order_id" not in indexes:
        op.create_index(
            "ix_user_subscriptions_razorpay_order_id",
            "user_subscriptions",
            ["razorpay_order_id"],
        )
    if "ix_user_subscriptions_razorpay_payment_id" not in indexes:
        op.create_index(
            "ix_user_subscriptions_razorpay_payment_id",
            "user_subscriptions",
            ["razorpay_payment_id"],
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute("DROP INDEX IF EXISTS ix_user_subscriptions_razorpay_payment_id")
        op.execute("DROP INDEX IF EXISTS ix_user_subscriptions_razorpay_order_id")
        op.execute(
            "ALTER TABLE user_subscriptions "
            "DROP COLUMN IF EXISTS payment_verified_at"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "DROP COLUMN IF EXISTS razorpay_payment_id"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "DROP COLUMN IF EXISTS razorpay_order_id"
        )
        op.execute(
            "ALTER TABLE user_subscriptions "
            "DROP COLUMN IF EXISTS payment_gateway"
        )
        return

    indexes = _indexes()
    if "ix_user_subscriptions_razorpay_payment_id" in indexes:
        op.drop_index(
            "ix_user_subscriptions_razorpay_payment_id",
            table_name="user_subscriptions",
        )
    if "ix_user_subscriptions_razorpay_order_id" in indexes:
        op.drop_index(
            "ix_user_subscriptions_razorpay_order_id",
            table_name="user_subscriptions",
        )

    columns = _columns()
    if "payment_verified_at" in columns:
        op.drop_column("user_subscriptions", "payment_verified_at")
    if "razorpay_payment_id" in columns:
        op.drop_column("user_subscriptions", "razorpay_payment_id")
    if "razorpay_order_id" in columns:
        op.drop_column("user_subscriptions", "razorpay_order_id")
    if "payment_gateway" in columns:
        op.drop_column("user_subscriptions", "payment_gateway")
