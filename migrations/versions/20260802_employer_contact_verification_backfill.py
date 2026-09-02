"""backfill employer contact verification flags

Revision ID: 20260802_emp_contact_verify
Revises: 20260801_add_max_published_jobs
Create Date: 2026-08-02 00:00:00.000000

"""

from alembic import op


revision = "20260802_emp_contact_verify"
down_revision = "20260801_add_max_published_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users AS u
        SET
            email_verified = TRUE,
            mobile_verified = TRUE,
            updated_at = CURRENT_TIMESTAMP
        FROM employer_profiles AS ep
        WHERE ep.user_id = u.user_id
          AND ep.is_deleted = 0
          AND (
              ep.is_verified = 1
              OR upper(ep.verification_status) IN ('APPROVED', 'VERIFIED')
          )
          AND (
              u.email_verified IS DISTINCT FROM TRUE
              OR u.mobile_verified IS DISTINCT FROM TRUE
          );
        """
    )


def downgrade() -> None:
    # Data-only backfill. Do not unset contact verification during downgrade.
    pass
