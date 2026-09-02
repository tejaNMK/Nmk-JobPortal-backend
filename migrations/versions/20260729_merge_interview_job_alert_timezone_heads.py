"""merge interview completed and job alert timezone heads

Revision ID: 20260729_merge_alert_tz_iv
Revises: 20260729_interview_completed_at, 20260729_job_alert_timezone
Create Date: 2026-07-29
"""


revision = "20260729_merge_alert_tz_iv"
down_revision = (
    "20260729_interview_completed_at",
    "20260729_job_alert_timezone",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
