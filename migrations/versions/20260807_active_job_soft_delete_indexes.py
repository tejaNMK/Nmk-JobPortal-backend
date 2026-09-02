"""add active job soft-delete indexes

Revision ID: 20260807_active_job_soft_delete_indexes
Revises: 20260806_candidate_search_engine_indexing
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_active_job_soft_delete_indexes"
down_revision = "20260806_candidate_search_engine_indexing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_jobs_active_employer_status_created_at",
        "jobs",
        ["employer_id", "status", "created_at"],
        unique=False,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_jobs_active_employer_status_created_at",
        table_name="jobs",
    )
