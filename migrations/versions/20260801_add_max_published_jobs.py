"""add max published jobs subscription limit

Revision ID: 20260801_add_max_published_jobs
Revises: 20260801_canonical_published_jobs
Create Date: 2026-08-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_add_max_published_jobs"
down_revision = "20260801_canonical_published_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("max_published_jobs", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE subscriptions
        SET max_published_jobs = max_job_posts
        WHERE upper(subscription_type) = 'EMPLOYER'
          AND max_published_jobs IS NULL
          AND max_job_posts IS NOT NULL
        """
    )
    op.drop_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        type_="check",
    )
    op.drop_column("subscriptions", "max_job_posts")
    op.create_check_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        """
        (max_published_jobs IS NULL OR max_published_jobs >= 0)
        AND (max_job_alerts IS NULL OR max_job_alerts >= 0)
        AND (max_resume_uploads IS NULL OR max_resume_uploads >= 0)
        """,
    )

def downgrade() -> None:
    op.drop_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        type_="check",
    )
    op.add_column(
        "subscriptions",
        sa.Column("max_job_posts", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE subscriptions
        SET max_job_posts = max_published_jobs
        WHERE upper(subscription_type) = 'EMPLOYER'
          AND max_job_posts IS NULL
          AND max_published_jobs IS NOT NULL
        """
    )
    op.drop_column("subscriptions", "max_published_jobs")
    op.create_check_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        """
        (max_job_posts IS NULL OR max_job_posts >= 0)
        AND (max_job_alerts IS NULL OR max_job_alerts >= 0)
        AND (max_resume_uploads IS NULL OR max_resume_uploads >= 0)
        """,
    )
