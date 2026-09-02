"""add unique active job posting index

Revision ID: 20260629_unique_active_job_posting
Revises: 20260629_add_job_closed_reason
Create Date: 2026-06-29
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8f1d7b5e2c49"
down_revision = "6e2f9c4a1b83"
branch_labels = None
depends_on = None


INDEX_NAME = "idx_jobs_unique_active_posting"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX_NAME}
        ON jobs (
            employer_id,
            lower(regexp_replace(btrim(coalesce(title, '')), '\\s+', ' ', 'g')),
            lower(regexp_replace(btrim(coalesce(company_name, '')), '\\s+', ' ', 'g')),
            lower(regexp_replace(btrim(coalesce(location, '')), '\\s+', ' ', 'g')),
            lower(regexp_replace(btrim(coalesce(employment_type, '')), '\\s+', ' ', 'g')),
            (created_at::date)
        )
        WHERE is_deleted IS FALSE
          AND status IN ('ACTIVE', 'PUBLISHED')
        """
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="jobs")
