"""Candidate and application template gap columns

Revision ID: 20260623_candidate_application_template_gaps
Revises: 8e5e7d0d8c39
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op


revision = "c51b10e0d510"
down_revision = "8e5e7d0d8c39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS candidate_profiles
            ADD COLUMN IF NOT EXISTS experience_level VARCHAR(100),
            ADD COLUMN IF NOT EXISTS current_company VARCHAR(255),
            ADD COLUMN IF NOT EXISTS notice_period VARCHAR(100),
            ADD COLUMN IF NOT EXISTS desired_employment VARCHAR(100),
            ADD COLUMN IF NOT EXISTS salary_expectation VARCHAR(100),
            ADD COLUMN IF NOT EXISTS work_preference VARCHAR(100),
            ADD COLUMN IF NOT EXISTS target_roles TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS job_applications
            ADD COLUMN IF NOT EXISTS referral_contact VARCHAR(255),
            ADD COLUMN IF NOT EXISTS next_step_text VARCHAR(500),
            ADD COLUMN IF NOT EXISTS next_step_due DATE,
            ADD COLUMN IF NOT EXISTS interview_loop_date DATE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS job_applications
            DROP COLUMN IF EXISTS interview_loop_date,
            DROP COLUMN IF EXISTS next_step_due,
            DROP COLUMN IF EXISTS next_step_text,
            DROP COLUMN IF EXISTS referral_contact
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS candidate_profiles
            DROP COLUMN IF EXISTS target_roles,
            DROP COLUMN IF EXISTS work_preference,
            DROP COLUMN IF EXISTS salary_expectation,
            DROP COLUMN IF EXISTS desired_employment,
            DROP COLUMN IF EXISTS notice_period,
            DROP COLUMN IF EXISTS current_company,
            DROP COLUMN IF EXISTS experience_level
        """
    )
