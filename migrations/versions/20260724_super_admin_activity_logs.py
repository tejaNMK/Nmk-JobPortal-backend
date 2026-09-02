"""create super admin activity logs

Revision ID: 20260724_activity_logs
Revises: 20260723_subscription_usage
Create Date: 2026-07-24 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_activity_logs"
down_revision = "20260723_subscription_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_logs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_role", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_activity_logs_actor_id",
        "activity_logs",
        ["actor_id"],
    )
    op.create_index(
        "idx_activity_logs_action",
        "activity_logs",
        ["action"],
    )
    op.create_index(
        "idx_activity_logs_created_at",
        "activity_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_activity_logs_created_at", table_name="activity_logs")
    op.drop_index("idx_activity_logs_action", table_name="activity_logs")
    op.drop_index("idx_activity_logs_actor_id", table_name="activity_logs")
    op.drop_table("activity_logs")
