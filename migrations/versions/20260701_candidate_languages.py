"""candidate_languages

Revision ID: 20260701_candidate_languages
Revises: 95e547b4302d
Create Date: 2026-07-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4a7e8d9c2f61"
down_revision = "8f1d7b5e2c49"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # =====================================================
    # candidate_resume_details
    # =====================================================

    op.execute("""
        ALTER TABLE candidate_resume_details
        ADD COLUMN IF NOT EXISTS languages_json JSONB
    """)


def downgrade() -> None:

    op.execute("""
        ALTER TABLE candidate_resume_details
        DROP COLUMN IF EXISTS languages_json
    """)