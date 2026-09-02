"""canonicalize published job status

Revision ID: 20260801_canonical_published_jobs
Revises: 20260801_remove_sub_enforce_flags
Create Date: 2026-08-01 00:00:00.000000
"""

from alembic import op


revision = "20260801_canonical_published_jobs"
down_revision = "20260801_remove_sub_enforce_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE jobs
        SET status = 'PUBLISHED',
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'ACTIVE'
        """
    )


def downgrade() -> None:
    pass
