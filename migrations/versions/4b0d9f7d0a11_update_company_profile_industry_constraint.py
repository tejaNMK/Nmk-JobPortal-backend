"""Allow both legacy and canonical company profile industry values."""

from alembic import op


revision = "4b0d9f7d0a11"
down_revision = "a1c6f4e0d235"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute("ALTER TABLE company_profiles DROP CONSTRAINT IF EXISTS chk_company_profiles_industry")
    op.execute(
        """
        ALTER TABLE company_profiles
        ADD CONSTRAINT chk_company_profiles_industry
        CHECK (
            industry IS NULL
            OR industry IN (
                'TECHNOLOGY', 'HEALTHCARE', 'FINANCE', 'EDUCATION', 'RETAIL',
                'MANUFACTURING', 'STAFFING', 'CONSULTING', 'OTHER'
            )
        )
        NOT VALID
        """
    )
