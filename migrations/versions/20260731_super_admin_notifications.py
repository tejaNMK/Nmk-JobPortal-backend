"""super admin notification fields

Revision ID: 20260731_sa_notifications
Revises: 20260730_candidate_resume_limit
Create Date: 2026-07-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_sa_notifications"
down_revision = "20260730_candidate_resume_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("recipient_user_id", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("recipient_role", sa.String(length=100), nullable=True))
    op.add_column("notifications", sa.Column("entity_type", sa.String(length=50), nullable=True))
    op.add_column("notifications", sa.Column("entity_id", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("target_route", sa.Text(), nullable=True))
    op.add_column("notifications", sa.Column("metadata", sa.JSON(), nullable=True))
    op.add_column("notifications", sa.Column("event_key", sa.Text(), nullable=True))
    op.add_column(
        "notifications",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.execute("UPDATE notifications SET recipient_user_id = recipient_id WHERE recipient_user_id IS NULL")

    op.create_index("idx_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("idx_notifications_type", "notifications", ["notification_type"])
    op.execute(
        "CREATE INDEX idx_notifications_recipient_read_created "
        "ON notifications (recipient_user_id, is_read, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_notifications_recipient_type_created "
        "ON notifications (recipient_user_id, notification_type, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_notifications_recipient_event_key "
        "ON notifications (recipient_user_id, event_key) "
        "WHERE event_key IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_recipient_event_key", table_name="notifications")
    op.drop_index("idx_notifications_recipient_type_created", table_name="notifications")
    op.drop_index("idx_notifications_recipient_read_created", table_name="notifications")
    op.drop_index("idx_notifications_type", table_name="notifications")
    op.drop_index("idx_notifications_recipient_user_id", table_name="notifications")

    op.drop_column("notifications", "updated_at")
    op.drop_column("notifications", "event_key")
    op.drop_column("notifications", "metadata")
    op.drop_column("notifications", "target_route")
    op.drop_column("notifications", "entity_id")
    op.drop_column("notifications", "entity_type")
    op.drop_column("notifications", "recipient_role")
    op.drop_column("notifications", "recipient_user_id")
