"""activity log timezone aware timestamps

Revision ID: 20260731_activity_tz
Revises: 20260731_sa_notifications
Create Date: 2026-07-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_activity_tz"
down_revision = "20260731_sa_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "activity_logs",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        existing_nullable=False,
        existing_server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "activity_logs",
        "created_at",
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
