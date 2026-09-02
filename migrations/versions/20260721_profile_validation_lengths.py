"""profile validation length constraints

Revision ID: e83f19aa2c07
Revises: c4d8e1f7a921
Create Date: 2026-07-21
"""

from alembic import op


revision = "e83f19aa2c07"
down_revision = "c4d8e1f7a921"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE company_profiles ALTER COLUMN website TYPE VARCHAR(255)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN description TYPE VARCHAR(2000)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN industry TYPE VARCHAR(100)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN size TYPE VARCHAR(20)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN size TYPE VARCHAR(20)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_country TYPE VARCHAR(100)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_state TYPE VARCHAR(100)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_city TYPE VARCHAR(100)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN contact_email TYPE VARCHAR(255)")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN verification_status TYPE VARCHAR(20)")

    op.execute("ALTER TABLE employer_profiles ALTER COLUMN linkedin_url TYPE VARCHAR(255)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN website_url TYPE VARCHAR(255)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN job_title TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN department TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN bio TYPE VARCHAR(1000)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN location TYPE VARCHAR(255)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN timezone TYPE VARCHAR(100)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN candidate_response_time TYPE VARCHAR(100)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN interview_mode TYPE VARCHAR(100)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN availability TYPE VARCHAR(500)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN visibility TYPE VARCHAR(20)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_1 TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_2 TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_3 TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_4 TYPE VARCHAR(150)")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN verification_status TYPE VARCHAR(20)")

    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_experience")
    op.execute(
        """
        ALTER TABLE employer_profiles
        ADD CONSTRAINT chk_employer_profile_experience
        CHECK (experience_years IS NULL OR (experience_years >= 0 AND experience_years <= 60))
        NOT VALID
        """
    )

    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_interview_mode")
    op.execute(
        """
        ALTER TABLE employer_profiles
        ADD CONSTRAINT chk_employer_profile_interview_mode
        CHECK (
            interview_mode IS NULL
            OR interview_mode IN ('PHONE', 'ONLINE', 'OFFLINE', 'HYBRID')
        )
        NOT VALID
        """
    )

    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_founded_year")
    op.execute(
        """
        ALTER TABLE company_profiles
        ADD CONSTRAINT chk_company_profiles_founded_year
        CHECK (
            founded_year IS NULL
            OR (
                founded_year >= 1900
                AND founded_year <= EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER
            )
        )
        NOT VALID
        """
    )

    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_industry")
    op.execute(
        """
        ALTER TABLE company_profiles
        ADD CONSTRAINT chk_company_profiles_industry
        CHECK (
            industry IS NULL
            OR industry IN (
                'IT', 'TECHNOLOGY', 'HEALTHCARE', 'FINANCE', 'EDUCATION', 'RETAIL',
                'MANUFACTURING', 'STAFFING', 'CONSULTING', 'OTHER'
            )
        )
        NOT VALID
        """
    )

    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_name")
    op.execute(
        """
        ALTER TABLE company_profiles
        ADD CONSTRAINT chk_company_profiles_name
        CHECK (
            company_name ~ $$^[A-Za-z0-9 &,.'()-]+$$
            AND length(btrim(company_name)) BETWEEN 2 AND 150
        )
        NOT VALID
        """
    )

    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_contact_phone")
    op.execute(
        r"""
        ALTER TABLE company_profiles
        ADD CONSTRAINT chk_company_profiles_contact_phone
        CHECK (contact_phone IS NULL OR contact_phone ~ '^\+[1-9]\d{7,14}$')
        NOT VALID
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_contact_phone")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_name")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_industry")
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_founded_year")
    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_interview_mode")
    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_experience")
    op.execute(
        """
        ALTER TABLE employer_profiles
        ADD CONSTRAINT chk_employer_profile_experience
        CHECK (experience_years IS NULL OR (experience_years >= 0 AND experience_years <= 50))
        NOT VALID
        """
    )

    op.execute("ALTER TABLE company_profiles ALTER COLUMN website TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN description TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN industry TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN size TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN size TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_country TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_state TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN headquarters_city TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN contact_email TYPE TEXT")
    op.execute("ALTER TABLE company_profiles ALTER COLUMN verification_status TYPE TEXT")

    op.execute("ALTER TABLE employer_profiles ALTER COLUMN linkedin_url TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN website_url TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN job_title TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN department TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN bio TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN location TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN timezone TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN candidate_response_time TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN interview_mode TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN availability TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN visibility TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_1 TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_2 TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_3 TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN specialization_4 TYPE TEXT")
    op.execute("ALTER TABLE employer_profiles ALTER COLUMN verification_status TYPE TEXT")