"""add job alert notification delivery dedup table

Revision ID: 20260729_job_alert_deliveries
Revises: 20260729_merge_logs_interviewers
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_job_alert_deliveries"
down_revision = "20260729_merge_logs_interviewers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_alert_notification_deliveries",
        sa.Column(
            "id",
            sa.Text(),
            server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.Text(), nullable=True),
        sa.Column("recipient_id", sa.Text(), nullable=False),
        sa.Column("alert_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(length=30), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("delivery_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "channel IN ('EMAIL', 'IN_APP')",
            name="chk_job_alert_notification_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="chk_job_alert_notification_deliveries_status",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.candidate_id"],
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["job_alerts.alert_id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_key",
            name="uq_job_alert_notification_deliveries_delivery_key",
        ),
    )
    op.create_index(
        "idx_job_alert_notification_deliveries_alert",
        "job_alert_notification_deliveries",
        ["alert_id"],
    )
    op.create_index(
        "idx_job_alert_notification_deliveries_recipient",
        "job_alert_notification_deliveries",
        ["recipient_id"],
    )
    op.create_index(
        "idx_job_alert_notification_deliveries_status",
        "job_alert_notification_deliveries",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_job_alert_notification_deliveries_status",
        table_name="job_alert_notification_deliveries",
    )
    op.drop_index(
        "idx_job_alert_notification_deliveries_recipient",
        table_name="job_alert_notification_deliveries",
    )
    op.drop_index(
        "idx_job_alert_notification_deliveries_alert",
        table_name="job_alert_notification_deliveries",
    )
    op.drop_table("job_alert_notification_deliveries")
