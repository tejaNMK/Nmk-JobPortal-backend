"""create user subscriptions table

Revision ID: db1ce015b7d7
Revises: bfded6275f37
Create Date: 2026-07-22 18:04:06.970566
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "db1ce015b7d7"
down_revision = "bfded6275f37"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "user_subscriptions",

        sa.Column(
            "user_subscription_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),

        sa.Column(
            "user_id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "subscription_id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "start_date",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),

        sa.Column(
            "end_date",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),

        sa.Column(
            "payment_status",
            sa.String(20),
            server_default=sa.text("'PAID'"),
            nullable=False,
        ),

        sa.Column(
            "auto_renew",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),

        sa.Column(
            "assigned_by",
            sa.UUID(),
            nullable=True,
        ),

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

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
        ),

        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.subscription_id"],
        ),

        sa.PrimaryKeyConstraint(
            "user_subscription_id",
        ),
    )


def downgrade() -> None:

    op.drop_table("user_subscriptions")