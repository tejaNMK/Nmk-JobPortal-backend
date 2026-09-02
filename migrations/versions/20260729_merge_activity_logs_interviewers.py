"""Merge activity logs and standalone interviewers heads.

Revision ID: 20260729_merge_logs_interviewers
Revises: 20260729_platform_activity_logs, 20260729_standalone_interviewers
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_merge_logs_interviewers"
down_revision = (
    "20260729_platform_activity_logs",
    "20260729_standalone_interviewers",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
