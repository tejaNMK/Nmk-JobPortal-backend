"""add currency-specific salary bands per country (US, UK, Canada,
Australia, Germany, Singapore, UAE) instead of sharing one generic $K
default list

Revision ID: 7c2e9f4a1d68
Revises: 5f8a3c1e9b47
Create Date: 2026-07-17 00:00:00.000000
"""

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c2e9f4a1d68"
down_revision = "5f8a3c1e9b47"
branch_labels = None
depends_on = None


# (country name, [bands in that country's local currency/convention])
# Illustrative bands, not exact market benchmarks -- adjust freely later,
# the same way India's LPA bands or the generic default list can be.
COUNTRY_SALARY_BANDS = [
    ("United States", [
        "$50K - $70K", "$70K - $90K", "$90K - $120K", "$120K - $150K", "$150K+",
    ]),
    ("United Kingdom", [
        "£30K - £45K", "£45K - £60K", "£60K - £80K", "£80K - £100K", "£100K+",
    ]),
    ("Canada", [
        "C$50K - C$70K", "C$70K - C$90K", "C$90K - C$120K", "C$120K - C$150K", "C$150K+",
    ]),
    ("Australia", [
        "A$60K - A$80K", "A$80K - A$100K", "A$100K - A$130K", "A$130K - A$160K", "A$160K+",
    ]),
    ("Germany", [
        "€40K - €55K", "€55K - €70K", "€70K - €90K", "€90K - €110K", "€110K+",
    ]),
    ("Singapore", [
        "S$50K - S$70K", "S$70K - S$90K", "S$90K - S$120K", "S$120K - S$150K", "S$150K+",
    ]),
    ("United Arab Emirates", [
        "AED 120K - AED 180K", "AED 180K - AED 240K", "AED 240K - AED 300K", "AED 300K - AED 400K", "AED 400K+",
    ]),
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
    for country_name, bands in COUNTRY_SALARY_BANDS:
        for idx, label in enumerate(bands):
            op.execute(
                "INSERT INTO master_salary_expectations (country_id, label, sort_order) "
                f"SELECT country_id, {_sql_literal(label)}, {idx} "
                "FROM master_countries "
                f"WHERE name = {_sql_literal(country_name)} "
                "ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING"
            )


def _downgrade_offline() -> None:
    for country_name, bands in COUNTRY_SALARY_BANDS:
        for label in bands:
            op.execute(
                "DELETE FROM master_salary_expectations "
                "WHERE country_id = ("
                "SELECT country_id FROM master_countries "
                f"WHERE name = {_sql_literal(country_name)}"
                ") "
                f"AND label = {_sql_literal(label)}"
            )


def upgrade() -> None:
    if context.is_offline_mode():
        _upgrade_offline()
        return

    conn = op.get_bind()

    for country_name, bands in COUNTRY_SALARY_BANDS:
        country_id = conn.execute(
            sa.text("SELECT country_id FROM master_countries WHERE name = :name"),
            {"name": country_name},
        ).scalar_one_or_none()

        if not country_id:
            continue  # country not seeded in this environment -- skip quietly

        for idx, label in enumerate(bands):
            conn.execute(
                sa.text("""
                    INSERT INTO master_salary_expectations (country_id, label, sort_order)
                    VALUES (:country_id, :label, :sort_order)
                    ON CONFLICT (COALESCE(country_id, ''), label) DO NOTHING
                """),
                {"country_id": country_id, "label": label, "sort_order": idx},
            )


def downgrade() -> None:
    if context.is_offline_mode():
        _downgrade_offline()
        return

    conn = op.get_bind()

    for country_name, bands in COUNTRY_SALARY_BANDS:
        country_id = conn.execute(
            sa.text("SELECT country_id FROM master_countries WHERE name = :name"),
            {"name": country_name},
        ).scalar_one_or_none()

        if not country_id:
            continue

        for label in bands:
            conn.execute(
                sa.text("DELETE FROM master_salary_expectations WHERE country_id = :country_id AND label = :label"),
                {"country_id": country_id, "label": label},
            )
