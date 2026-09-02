"""subscription enforcement fixes

Revision ID: 20260730_sub_enforce
Revises: 20260729_standalone_interviewers, 20260729_merge_alert_tz_iv
Create Date: 2026-07-30 00:00:00.000000
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20260730_sub_enforce"
down_revision = ("20260729_standalone_interviewers", "20260729_merge_alert_tz_iv")
branch_labels = None
depends_on = None


CANDIDATE_DEFAULT_FEATURES = {
    "job_alerts": True,
    "max_job_alerts": None,
    "resume_builder": True,
    "resume_upload": True,
    "resume_visibility": True,
    "saved_jobs": True,
    "saved_jobs_limit": 30,
    "unlimited_job_applications": True,
}

EMPLOYER_DEFAULT_FEATURES = {
    "candidate_invitations": True,
    "candidate_search": True,
    "resume_downloads": True,
    "unlimited_job_posts": True,
}


def _merge_default_features(subscription_type: str, features: dict) -> None:
    feature_json = json.dumps(features, sort_keys=True)
    op.execute(
        f"""
        UPDATE subscriptions
        SET feature_flags = (
                COALESCE(feature_flags::jsonb, '{{}}'::jsonb)
                || '{feature_json}'::jsonb
            )::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE upper(subscription_type) = '{subscription_type}'
          AND is_default = true
        """
    )


def upgrade() -> None:
    op.add_column(
        "job_applications",
        sa.Column("resume_file_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("resume_blob_ref_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("resume_file_path_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("resume_file_size_snapshot", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE job_applications AS app
        SET resume_file_name_snapshot = resume.file_name,
            resume_blob_ref_snapshot = resume.blob_ref,
            resume_file_path_snapshot = resume.file_path,
            resume_file_size_snapshot = resume.file_size
        FROM candidate_resumes AS resume
        WHERE app.resume_id = resume.resume_id
          AND app.resume_file_name_snapshot IS NULL
        """
    )

    _merge_default_features("CANDIDATE", CANDIDATE_DEFAULT_FEATURES)
    _merge_default_features("EMPLOYER", EMPLOYER_DEFAULT_FEATURES)


def downgrade() -> None:
    op.drop_column("job_applications", "resume_file_size_snapshot")
    op.drop_column("job_applications", "resume_file_path_snapshot")
    op.drop_column("job_applications", "resume_blob_ref_snapshot")
    op.drop_column("job_applications", "resume_file_name_snapshot")
