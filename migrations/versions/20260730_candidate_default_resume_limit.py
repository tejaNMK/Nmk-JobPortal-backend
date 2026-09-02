"""candidate default resume limit

Revision ID: 20260730_candidate_resume_limit
Revises: 20260730_sub_enforce
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op


revision = "20260730_candidate_resume_limit"
down_revision = "20260730_sub_enforce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE subscriptions
        SET max_resume_uploads = 5,
            updated_at = CURRENT_TIMESTAMP
        WHERE upper(subscription_type) = 'CANDIDATE'
          AND is_default = true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE subscriptions
        SET max_resume_uploads = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE upper(subscription_type) = 'CANDIDATE'
          AND is_default = true
          AND max_resume_uploads = 5
        """
    )
