"""remove system settings extra config

Revision ID: 20260727_remove_extra_config
Revises: 20260727_job_alert_title
Create Date: 2026-07-27 17:10:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260727_remove_extra_config"
down_revision = "20260727_job_alert_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS extra_config")
        return

    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("system_settings")
    }
    if "extra_config" in columns:
        op.drop_column("system_settings", "extra_config")


def downgrade() -> None:
    if context.is_offline_mode():
        op.execute(
            "ALTER TABLE system_settings "
            "ADD COLUMN IF NOT EXISTS extra_config JSON DEFAULT '{}' NOT NULL"
        )
        return

    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("system_settings")
    }
    if "extra_config" not in columns:
        op.add_column(
            "system_settings",
            sa.Column(
                "extra_config",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
        )
