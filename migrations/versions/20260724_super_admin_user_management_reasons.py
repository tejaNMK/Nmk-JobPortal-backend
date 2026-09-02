"""add super admin user management reason fields

Revision ID: 20260724_user_mgmt_reasons
Revises: 20260724_activity_logs
Create Date: 2026-07-24 19:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_user_mgmt_reasons"
down_revision = "20260724_activity_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_profiles",
        sa.Column("suspension_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "employer_profiles",
        sa.Column("suspension_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "employer_profiles",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employer_profiles", "rejection_reason")
    op.drop_column("employer_profiles", "suspension_reason")
    op.drop_column("candidate_profiles", "suspension_reason")
