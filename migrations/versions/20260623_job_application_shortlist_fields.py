"""add user and job application fields

Revision ID: add_user_job_fields
Revises: 20260623_candidate_application_template_gaps
Create Date: 2026-06-23
"""

from alembic import op


revision = "add_user_job_fields"
down_revision = "c51b10e0d510"
branch_labels = None
depends_on = None


def upgrade():

    # users
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100)
    """)

    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS country_code VARCHAR(10) DEFAULT '+91'
    """)

    # job_applications
    op.execute("""
        ALTER TABLE job_applications
        ADD COLUMN IF NOT EXISTS candidate_rating INTEGER
    """)

    op.execute("""
        ALTER TABLE job_applications
        ADD COLUMN IF NOT EXISTS shortlisted_at TIMESTAMP
    """)

    op.execute("""
        ALTER TABLE job_applications
        ADD COLUMN IF NOT EXISTS recruiter_notes TEXT
    """)


def downgrade():

    op.execute("""
        ALTER TABLE job_applications
        DROP COLUMN IF EXISTS recruiter_notes
    """)

    op.execute("""
        ALTER TABLE job_applications
        DROP COLUMN IF EXISTS shortlisted_at
    """)

    op.execute("""
        ALTER TABLE job_applications
        DROP COLUMN IF EXISTS candidate_rating
    """)

    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS country_code
    """)

    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS middle_name
    """)