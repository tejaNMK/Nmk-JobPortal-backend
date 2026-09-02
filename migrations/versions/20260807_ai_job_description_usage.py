"""add ai job description usage

Revision ID: 20260807_ai_job_description_usage
Revises: 20260807_active_job_soft_delete_indexes
Create Date: 2026-08-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260807_ai_job_description_usage"
down_revision = "20260807_active_job_soft_delete_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_job_description_usage",
        sa.Column(
            "usage_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "employer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Text(),
            sa.ForeignKey("employer_profiles.id"),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=True),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("request_status", sa.String(length=20), nullable=False, server_default=sa.text("'SUCCESS'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "idx_ai_job_description_usage_user_created",
        "ai_job_description_usage",
        ["employer_user_id", "created_at"],
    )
    op.create_index(
        "idx_ai_job_description_usage_company_created",
        "ai_job_description_usage",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_ai_job_description_usage_company_created",
        table_name="ai_job_description_usage",
    )
    op.drop_index(
        "idx_ai_job_description_usage_user_created",
        table_name="ai_job_description_usage",
    )
    op.drop_table("ai_job_description_usage")
