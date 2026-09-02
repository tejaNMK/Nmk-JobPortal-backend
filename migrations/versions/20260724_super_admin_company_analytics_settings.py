"""add super admin company approvals analytics settings

Revision ID: 20260724_company_settings
Revises: 20260724_user_mgmt_reasons
Create Date: 2026-07-24 20:30:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260724_company_settings"
down_revision = "20260724_user_mgmt_reasons"
branch_labels = None
depends_on = None


def _upgrade_offline() -> None:
    op.execute("ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    op.execute("ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP")
    op.execute("ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
    op.execute("ALTER TABLE employer_profiles ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP")
    op.execute("ALTER TABLE employer_profiles ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP")
    op.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            maintenance_mode BOOLEAN DEFAULT false NOT NULL,
            registration_enabled BOOLEAN DEFAULT true NOT NULL,
            default_subscription_plan VARCHAR(150),
            password_policy JSON DEFAULT '{}' NOT NULL,
            email_notifications JSON DEFAULT '{}' NOT NULL,
            platform_config JSON DEFAULT '{}' NOT NULL,
            extra_config JSON DEFAULT '{}' NOT NULL,
            is_active BOOLEAN DEFAULT true NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_by TEXT,
            PRIMARY KEY (id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_system_settings_is_active "
        "ON system_settings (is_active)"
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _upgrade_offline()
        return

    inspector = sa.inspect(op.get_bind())
    company_columns = {
        column["name"] for column in inspector.get_columns("company_profiles")
    }
    employer_columns = {
        column["name"] for column in inspector.get_columns("employer_profiles")
    }

    if "approved_at" not in company_columns:
        op.add_column(
            "company_profiles",
            sa.Column("approved_at", sa.DateTime(), nullable=True),
        )
    if "rejected_at" not in company_columns:
        op.add_column(
            "company_profiles",
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
        )
    if "rejection_reason" not in company_columns:
        op.add_column(
            "company_profiles",
            sa.Column("rejection_reason", sa.Text(), nullable=True),
        )
    if "approved_at" not in employer_columns:
        op.add_column(
            "employer_profiles",
            sa.Column("approved_at", sa.DateTime(), nullable=True),
        )
    if "rejected_at" not in employer_columns:
        op.add_column(
            "employer_profiles",
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
        )

    if "system_settings" not in inspector.get_table_names():
        op.create_table(
            "system_settings",
            sa.Column(
                "id",
                sa.UUID(),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column(
                "maintenance_mode",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "registration_enabled",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("default_subscription_plan", sa.String(length=150), nullable=True),
            sa.Column(
                "password_policy",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column(
                "email_notifications",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column(
                "platform_config",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column(
                "extra_config",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
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
            sa.Column("updated_by", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_system_settings_is_active",
            "system_settings",
            ["is_active"],
        )


def downgrade() -> None:
    op.drop_index("idx_system_settings_is_active", table_name="system_settings")
    op.drop_table("system_settings")
    op.drop_column("employer_profiles", "rejected_at")
    op.drop_column("employer_profiles", "approved_at")
    op.drop_column("company_profiles", "rejection_reason")
    op.drop_column("company_profiles", "rejected_at")
    op.drop_column("company_profiles", "approved_at")
