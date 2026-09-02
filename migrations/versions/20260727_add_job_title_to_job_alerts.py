"""add job title to job alerts

Revision ID: 20260727_job_alert_title
Revises: 20260724_company_settings
Create Date: 2026-07-27

"""

from alembic import op


revision = "20260727_job_alert_title"
down_revision = "20260724_company_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS job_title VARCHAR(100);
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE job_alerts
    DROP COLUMN IF EXISTS job_title;
    """)
