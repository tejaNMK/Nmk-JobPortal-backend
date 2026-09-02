"""subscription assignment history and usage

Revision ID: 20260723_subscription_usage
Revises: 74d7cf5ece8b
Create Date: 2026-07-23 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_subscription_usage"
down_revision = "74d7cf5ece8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "feature_flags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "role",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'CANDIDATE'"),
        ),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "uq_user_subscriptions_one_active",
        "user_subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "subscription_history",
        sa.Column(
            "history_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_subscription_id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.Column("old_start_date", sa.DateTime(), nullable=True),
        sa.Column("old_end_date", sa.DateTime(), nullable=True),
        sa.Column("new_start_date", sa.DateTime(), nullable=True),
        sa.Column("new_end_date", sa.DateTime(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_subscription_id"], ["user_subscriptions.user_subscription_id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.subscription_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("history_id"),
    )

    op.create_table(
        "subscription_usage",
        sa.Column(
            "usage_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_subscription_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("feature_name", sa.String(100), nullable=False),
        sa.Column("used_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_subscription_id"], ["user_subscriptions.user_subscription_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("usage_id"),
        sa.UniqueConstraint(
            "user_subscription_id",
            "feature_name",
            name="uq_subscription_usage_feature",
        ),
    )


def downgrade() -> None:
    op.drop_table("subscription_usage")
    op.drop_table("subscription_history")
    op.drop_index("uq_user_subscriptions_one_active", table_name="user_subscriptions")
    op.drop_column("user_subscriptions", "cancelled_at")
    op.drop_column("user_subscriptions", "role")
    op.drop_column("subscriptions", "feature_flags")
