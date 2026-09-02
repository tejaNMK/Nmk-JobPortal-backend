"""add currency_code to master_countries (backfilled from CLDR/ISO-4217
territory-currency data) so currency-aware UI (Current/Expected Salary
hints, etc.) works for every seeded country, not just the 8 hand-curated
ones

Revision ID: 9a1d5e7c3f82
Revises: 7c2e9f4a1d68
Create Date: 2026-07-17 00:00:00.000000
"""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a1d5e7c3f82"
down_revision = "7c2e9f4a1d68"
branch_labels = None
depends_on = None

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"


def upgrade() -> None:
    conn = op.get_bind()

    op.execute("ALTER TABLE master_countries ADD COLUMN IF NOT EXISTS currency_code VARCHAR(3)")

    currency_by_iso2 = json.loads((SEED_DIR / "country_currencies.json").read_text(encoding="utf-8"))

    for iso2, currency_code in currency_by_iso2.items():
        conn.execute(
            sa.text("""
                UPDATE master_countries
                SET currency_code = :currency_code
                WHERE iso_code = :iso2 AND currency_code IS NULL
            """),
            {"iso2": iso2, "currency_code": currency_code},
        )


def downgrade() -> None:
    op.execute("ALTER TABLE master_countries DROP COLUMN IF EXISTS currency_code")