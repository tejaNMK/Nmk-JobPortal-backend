"""scope master_salary_expectations by country (fixes US candidates
seeing India-only LPA salary bands) + seed US/default K-format bands

Revision ID: 5f8a3c1e9b47
Revises: 035df0e4e40e
Create Date: 2026-07-17 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5f8a3c1e9b47"
down_revision = "035df0e4e40e"
branch_labels = None
depends_on = None


# Country-agnostic fallback, used for every country that doesn't have its
# own dedicated bands (currently: everyone except India). This is what
# fixes the reported bug -- US candidates (and any other non-India
# candidate) now see K-format bands instead of India's LPA bands.
DEFAULT_SALARY_BANDS = [
    "$50K - $70K",
    "$70K - $90K",
    "$90K - $120K",
    "$120K - $150K",
    "$150K+",
]


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"

    parts = []
    ascii_buffer = []
    for char in str(value):
        if ord(char) < 128:
            ascii_buffer.append(char)
            continue

        if ascii_buffer:
            parts.append("'" + "".join(ascii_buffer).replace("'", "''") + "'")
            ascii_buffer = []
        parts.append(f"chr({ord(char)})")

    if ascii_buffer:
        parts.append("'" + "".join(ascii_buffer).replace("'", "''") + "'")

    return " || ".join(parts) if parts else "''"


def _upgrade_offline() -> None:
    op.execute("""
        ALTER TABLE master_salary_expectations
        ADD COLUMN IF NOT EXISTS country_id TEXT REFERENCES master_countries(country_id)
    """)

    op.drop_index("idx_master_salary_expectations_label", table_name="master_salary_expectations")

    op.execute("""
        UPDATE master_salary_expectations
        SET country_id = (
            SELECT country_id FROM master_countries WHERE name = 'India'
        )
        WHERE country_id IS NULL
          AND EXISTS (
              SELECT 1 FROM master_countries WHERE name = 'India'
          )
    """)

    op.create_index(
        "idx_master_salary_expectations_country_label",
        "master_salary_expectations",
        [sa.text("COALESCE(country_id, '')"), "label"],
        unique=True,
    )

    for idx, label in enumerate(DEFAULT_SALARY_BANDS):
        op.execute(
            "INSERT INTO master_salary_expectations (country_id, label, sort_order) "
            f"VALUES (NULL, {_sql_literal(label)}, {idx}) "
            "ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING"
        )


def upgrade() -> None:
    if context.is_offline_mode():
        _upgrade_offline()
        return

    conn = op.get_bind()

    # =====================================================
    # master_salary_expectations - add country scoping
    # =====================================================
    op.execute("ALTER TABLE master_salary_expectations ADD COLUMN IF NOT EXISTS country_id TEXT REFERENCES master_countries(country_id)")

    op.drop_index("idx_master_salary_expectations_label", table_name="master_salary_expectations")

    # Existing rows ("3-5 LPA", etc.) were India-specific in practice even
    # though nothing enforced that -- pin them to India explicitly instead
    # of leaving them as the accidental global default every country fell
    # back to (which is the bug being fixed here).
    india_id = conn.execute(
        sa.text("SELECT country_id FROM master_countries WHERE name = 'India'")
    ).scalar_one_or_none()
    if india_id:
        conn.execute(
            sa.text("UPDATE master_salary_expectations SET country_id = :india_id WHERE country_id IS NULL"),
            {"india_id": india_id},
        )

    op.create_index(
        "idx_master_salary_expectations_country_label",
        "master_salary_expectations",
        [sa.text("COALESCE(country_id, '')"), "label"],
        unique=True,
    )

    # =====================================================
    # Seed the country-agnostic default (K-format) bands
    # =====================================================
    for idx, label in enumerate(DEFAULT_SALARY_BANDS):
        conn.execute(
            sa.text("""
                INSERT INTO master_salary_expectations (country_id, label, sort_order)
                VALUES (NULL, :label, :sort_order)
                ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING
            """),
            {"label": label, "sort_order": idx},
        )


def downgrade() -> None:
    conn = op.get_bind()

    for label in DEFAULT_SALARY_BANDS:
        conn.execute(
            sa.text("DELETE FROM master_salary_expectations WHERE country_id IS NULL AND label = :label"),
            {"label": label},
        )

    op.drop_index("idx_master_salary_expectations_country_label", table_name="master_salary_expectations")

    # Revert India's rows back to country-agnostic so the old unique index
    # on label alone can be recreated without collisions.
    op.execute("UPDATE master_salary_expectations SET country_id = NULL")

    op.create_index("idx_master_salary_expectations_label", "master_salary_expectations", ["label"], unique=True)

    op.execute("ALTER TABLE master_salary_expectations DROP COLUMN IF EXISTS country_id")
