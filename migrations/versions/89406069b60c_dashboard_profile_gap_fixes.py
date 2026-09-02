"""dashboard_profile_gap_fixes

Revision ID: 89406069b60c
Revises: b0d0006fc1bf
Create Date: 2026-06-24 19:32:04.991240

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "89406069b60c"
down_revision = "b0d0006fc1bf"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # =====================================================
    # users
    # =====================================================

    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS cover_image_url TEXT
    """)

    # =====================================================
    # candidate_profiles
    # =====================================================

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS open_to_work BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS active_resume_id TEXT
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS profile_completion_pct INTEGER NOT NULL DEFAULT 0
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS website_url TEXT
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS portfolio_url TEXT
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS dribbble_url TEXT
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS twitter_url TEXT
    """)

    # remove obsolete field if it exists
    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS public_profile_url
    """)

    # =====================================================
    # jobs
    # =====================================================

    op.execute("""
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS salary_currency VARCHAR(10)
        NOT NULL DEFAULT 'USD'
    """)

    op.execute("""
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS salary_period VARCHAR(20)
        NOT NULL DEFAULT 'Monthly'
    """)

    # =====================================================
    # candidate_resume_details
    # =====================================================

    op.execute("""
        ALTER TABLE candidate_resume_details
        ADD COLUMN IF NOT EXISTS projects_json JSONB
    """)

    # =====================================================
    # profile_view_events
    # =====================================================

    op.execute("""
        CREATE TABLE IF NOT EXISTS profile_view_events (
            view_id TEXT PRIMARY KEY
                DEFAULT replace(gen_random_uuid()::text, '-', ''),

            candidate_id TEXT NOT NULL
                REFERENCES candidate_profiles(candidate_id),

            viewer_user_id UUID
                REFERENCES users(user_id),

            viewer_ip TEXT,

            viewed_at TIMESTAMP NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pve_candidate_id
        ON profile_view_events(candidate_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pve_viewed_at
        ON profile_view_events(viewed_at)
    """)

    # =====================================================
    # candidate_company_followings
    # =====================================================

    op.execute("""
        CREATE TABLE IF NOT EXISTS candidate_company_followings (
            following_id TEXT PRIMARY KEY
                DEFAULT replace(gen_random_uuid()::text, '-', ''),

            candidate_id TEXT NOT NULL
                REFERENCES candidate_profiles(candidate_id),

            company_id TEXT NOT NULL
                REFERENCES company_profiles(company_id),

            followed_at TIMESTAMP NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            is_deleted BOOLEAN NOT NULL
                DEFAULT FALSE,

            deleted_at TIMESTAMP
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ccf_candidate_id
        ON candidate_company_followings(candidate_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ccf_company_id
        ON candidate_company_followings(company_id)
    """)


def downgrade() -> None:

    op.execute("""
        DROP INDEX IF EXISTS idx_ccf_company_id
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_ccf_candidate_id
    """)

    op.execute("""
        DROP TABLE IF EXISTS candidate_company_followings
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_pve_viewed_at
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_pve_candidate_id
    """)

    op.execute("""
        DROP TABLE IF EXISTS profile_view_events
    """)

    op.execute("""
        ALTER TABLE candidate_resume_details
        DROP COLUMN IF EXISTS projects_json
    """)

    op.execute("""
        ALTER TABLE jobs
        DROP COLUMN IF EXISTS salary_period
    """)

    op.execute("""
        ALTER TABLE jobs
        DROP COLUMN IF EXISTS salary_currency
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS twitter_url
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS dribbble_url
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS portfolio_url
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS website_url
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS profile_completion_pct
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS active_resume_id
    """)

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS open_to_work
    """)

    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS cover_image_url
    """)