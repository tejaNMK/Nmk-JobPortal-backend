"""add search engine indexing to candidate profiles

Revision ID: 20260806_candidate_search_engine_indexing
Revises: 20260805_users_phone_country_iso2
Create Date: 2026-08-06 00:00:00.000000
"""

from alembic import op


revision = "20260806_candidate_search_engine_indexing"
down_revision = "20260805_users_phone_country_iso2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE candidate_profiles
    ADD COLUMN IF NOT EXISTS search_engine_indexing BOOLEAN NOT NULL DEFAULT FALSE;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE candidate_profiles
    DROP COLUMN IF EXISTS search_engine_indexing;
    """)
