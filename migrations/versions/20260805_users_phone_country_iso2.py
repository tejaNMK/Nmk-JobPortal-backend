"""add phone country iso2 to users

Revision ID: 20260805_users_phone_country_iso2
Revises: 20260804_weekly_sub_usage
Create Date: 2026-08-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_users_phone_country_iso2"
down_revision = "20260804_weekly_sub_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_country_iso2", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone_country_iso2")
