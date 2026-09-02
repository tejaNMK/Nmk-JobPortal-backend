"""add follow notifications enabled to candidate profiles

Revision ID: 20260728_follow_notify
Revises: 20260727_subscription_defaults
Create Date: 2026-07-28

"""

from alembic import op


revision = "20260728_follow_notify"
down_revision = "20260727_subscription_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE candidate_profiles
    ADD COLUMN IF NOT EXISTS follow_notifications_enabled BOOLEAN NOT NULL DEFAULT FALSE;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE candidate_profiles
    DROP COLUMN IF EXISTS follow_notifications_enabled;
    """)