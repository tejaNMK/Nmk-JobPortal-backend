"""company and employer profile modules

Revision ID: 20260713_profiles
Revises: b7e2c4a9f103
Create Date: 2026-07-13 00:00:00.000000

"""

from alembic import op


revision = "20260713_profiles"
down_revision = "f2b6c1d9a834"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS job_title TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS department TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS bio TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS location TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS timezone TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS experience_years INTEGER
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS candidate_response_time TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS interview_mode TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS availability TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS languages JSONB
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS website_url TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS profile_photo TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'PRIVATE'
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS specialization_1 TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS specialization_2 TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS specialization_3 TEXT
    """)
    op.execute("""
        ALTER TABLE employer_profiles
        ADD COLUMN IF NOT EXISTS specialization_4 TEXT
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_employer_profile_experience'
            ) THEN
                ALTER TABLE employer_profiles
                ADD CONSTRAINT chk_employer_profile_experience
                CHECK (experience_years IS NULL OR (experience_years >= 0 AND experience_years <= 50))
                NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_employer_profile_visibility'
            ) THEN
                ALTER TABLE employer_profiles
                ADD CONSTRAINT chk_employer_profile_visibility
                CHECK (visibility IN ('PUBLIC', 'PRIVATE', 'COMPANY_ONLY'))
                NOT VALID;
            END IF;
        END $$;
    """)

    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid()
    """)
    op.execute("""
        UPDATE company_profiles
        SET id = gen_random_uuid()
        WHERE id IS NULL
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS logo_url TEXT
    """)
    op.execute("""
        UPDATE company_profiles
        SET logo_url = logo_path
        WHERE logo_url IS NULL AND logo_path IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS company_size TEXT
    """)
    op.execute("""
        UPDATE company_profiles
        SET company_size = size
        WHERE company_size IS NULL AND size IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS founded_year INTEGER
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS headquarters_country TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS headquarters_state TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS headquarters_city TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS contact_email TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(20)
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'PENDING'
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS created_by TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ADD COLUMN IF NOT EXISTS updated_by TEXT
    """)
    op.execute("""
        ALTER TABLE company_profiles
        ALTER COLUMN company_id SET DEFAULT replace(gen_random_uuid()::text, '-', '')
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_company_profiles_id'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT uq_company_profiles_id UNIQUE (id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_company_profiles_company_id'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT uq_company_profiles_company_id UNIQUE (company_id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_company_profiles_employer_id'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT uq_company_profiles_employer_id UNIQUE (employer_id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_company_profiles_size'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT chk_company_profiles_size
                CHECK (company_size IS NULL OR company_size IN ('1-10', '11-50', '51-200', '201-500', '500+'))
                NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_company_profiles_verification'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT chk_company_profiles_verification
                CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED'))
                NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_company_profiles_founded_year'
            ) THEN
                ALTER TABLE company_profiles
                ADD CONSTRAINT chk_company_profiles_founded_year
                CHECK (founded_year IS NULL OR founded_year >= 1800)
                NOT VALID;
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_profiles_public
        ON company_profiles(is_public)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_profiles_industry
        ON company_profiles(industry)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_company_profiles_verification
        ON company_profiles(verification_status)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_company_profiles_verification")
    op.execute("DROP INDEX IF EXISTS idx_company_profiles_industry")
    op.execute("DROP INDEX IF EXISTS idx_company_profiles_public")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_founded_year")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_verification")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_size")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS uq_company_profiles_employer_id")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS uq_company_profiles_company_id")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS uq_company_profiles_id")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS updated_by")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS is_public")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS verified_at")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS verification_status")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS contact_phone")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS contact_email")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS headquarters_city")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS headquarters_state")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS headquarters_country")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS founded_year")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS company_size")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS logo_url")
    op.execute("ALTER TABLE company_profiles DROP COLUMN IF EXISTS id")

    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_visibility")
    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_experience")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS specialization_4")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS specialization_3")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS specialization_2")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS specialization_1")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS visibility")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS profile_photo")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS website_url")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS languages")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS availability")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS interview_mode")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS candidate_response_time")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS experience_years")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS timezone")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS location")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS bio")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS department")
    op.execute("ALTER TABLE employer_profiles DROP COLUMN IF EXISTS job_title")
