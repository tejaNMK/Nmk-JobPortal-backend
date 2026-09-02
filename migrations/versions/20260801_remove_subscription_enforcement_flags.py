"""remove unused subscription enforcement flags

Revision ID: 20260801_remove_sub_enforce_flags
Revises: 20260801_sub_api_integrity
Create Date: 2026-08-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_remove_sub_enforce_flags"
down_revision = "20260801_sub_api_integrity"
branch_labels = None
depends_on = None


REMOVED_FEATURE_KEYS = (
    "companyProfile",
    "company_profile",
    "jobPosting",
    "job_posting",
    "maxActiveJobPosts",
    "max_active_job_posts",
    "maxCandidateSearches",
    "max_candidate_searches",
    "maxJobApplications",
    "max_job_applications",
    "resumeDownloads",
    "resume_downloads",
    "resumeUpload",
    "resume_upload",
    "unlimitedJobPosts",
    "unlimited_job_posts",
    "unlimitedJobApplications",
    "unlimited_job_applications",
)


def upgrade() -> None:
    keys_sql = ", ".join(f"'{key}'" for key in REMOVED_FEATURE_KEYS)
    op.execute(
        f"""
        UPDATE subscriptions
        SET feature_flags = (
                COALESCE(feature_flags::jsonb, '{{}}'::jsonb)
                - ARRAY[{keys_sql}]
            )::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE feature_flags IS NOT NULL
        """
    )
    op.drop_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        type_="check",
    )
    op.drop_column("subscriptions", "max_candidate_searches")
    op.create_check_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        """
        (max_job_posts IS NULL OR max_job_posts >= 0)
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
        sa.Column("max_candidate_searches", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        """
        (max_job_posts IS NULL OR max_job_posts >= 0)
        AND (max_job_alerts IS NULL OR max_job_alerts >= 0)
        AND (max_resume_uploads IS NULL OR max_resume_uploads >= 0)
        AND (max_candidate_searches IS NULL OR max_candidate_searches >= 0)
        """,
    )
