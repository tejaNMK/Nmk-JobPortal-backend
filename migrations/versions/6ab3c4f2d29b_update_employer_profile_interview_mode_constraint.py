"""Allow both legacy and canonical employer interview mode values."""

from alembic import op


revision = "6ab3c4f2d29b"
down_revision = "4b0d9f7d0a11"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute("ALTER TABLE employer_profiles DROP CONSTRAINT IF EXISTS chk_employer_profile_interview_mode")
    op.execute(
        """
        ALTER TABLE employer_profiles
        ADD CONSTRAINT chk_employer_profile_interview_mode
        CHECK (interview_mode IS NULL OR interview_mode IN ('PHONE', 'ONLINE', 'OFFLINE', 'HYBRID'))
        NOT VALID
        """
    )
