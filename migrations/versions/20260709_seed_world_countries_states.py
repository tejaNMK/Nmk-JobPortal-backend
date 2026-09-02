"""seed full world countries + states/provinces (replaces the 8-country
starter list with ~250 countries and ~5,300 states/provinces so the Country
and Primary/Preferred Location dropdowns can cover every country)

Revision ID: b7e2c4a9f103
Revises: 9d4f1a6b8c23
Create Date: 2026-07-09 00:00:00.000000

"""
import json
from pathlib import Path

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7e2c4a9f103"
down_revision = "9d4f1a6b8c23"
branch_labels = None
depends_on = None

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_data"


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


def _load_seed_data() -> tuple[list[dict], dict[str, list[str]]]:
    countries = json.loads((SEED_DIR / "world_countries.json").read_text(encoding="utf-8"))
    states_by_iso2 = json.loads((SEED_DIR / "world_states.json").read_text(encoding="utf-8"))
    return countries, states_by_iso2


def _upgrade_offline(countries: list[dict], states_by_iso2: dict[str, list[str]]) -> None:
    country_name_by_iso2 = {}

    for idx, c in enumerate(countries):
        name = c["name"]
        iso2 = c["iso2"]
        phonecode = c.get("phonecode")
        if not name or not iso2:
            continue

        country_name_by_iso2[iso2] = name
        op.execute(
            "INSERT INTO master_countries (name, iso_code, phone_code, sort_order) "
            f"VALUES ({_sql_literal(name)}, {_sql_literal(iso2)}, "
            f"{_sql_literal(phonecode)}, {100 + idx}) "
            "ON CONFLICT (name) DO UPDATE SET "
            "iso_code = COALESCE(master_countries.iso_code, EXCLUDED.iso_code), "
            "phone_code = COALESCE(master_countries.phone_code, EXCLUDED.phone_code)"
        )

    for iso2, state_names in states_by_iso2.items():
        country_name = country_name_by_iso2.get(iso2)
        if not country_name:
            continue

        for state_idx, state_name in enumerate(state_names):
            if not state_name:
                continue
            op.execute(
                "INSERT INTO master_locations (country_id, name, sort_order) "
                f"SELECT country_id, CAST({_sql_literal(state_name)} AS VARCHAR), {state_idx} "
                "FROM master_countries "
                f"WHERE name = {_sql_literal(country_name)} "
                "ON CONFLICT (country_id, name) DO NOTHING"
            )


def upgrade() -> None:
    countries, states_by_iso2 = _load_seed_data()

    if context.is_offline_mode():
        _upgrade_offline(countries, states_by_iso2)
        return

    conn = op.get_bind()

    # Existing 8 countries were seeded starting at sort_order 0-7 with a
    # handful of cities under them. Push the full world list in after those
    # (sort_order continues from 100) so the original "quick pick" countries
    # still float to the top of the dropdown, while every other country in
    # the world is now present and searchable underneath.
    country_id_by_iso2 = {}

    for idx, c in enumerate(countries):
        name = c["name"]
        iso2 = c["iso2"]
        phonecode = c.get("phonecode")
        if not name or not iso2:
            continue

        result = conn.execute(
            sa.text("""
                INSERT INTO master_countries (name, iso_code, phone_code, sort_order)
                VALUES (:name, :iso_code, :phone_code, :sort_order)
                ON CONFLICT (name) DO UPDATE SET
                    iso_code = COALESCE(master_countries.iso_code, EXCLUDED.iso_code),
                    phone_code = COALESCE(master_countries.phone_code, EXCLUDED.phone_code)
                RETURNING country_id
            """),
            {
                "name": name,
                "iso_code": iso2,
                "phone_code": phonecode,
                "sort_order": 100 + idx,
            },
        )
        country_id_by_iso2[iso2] = result.scalar_one()

    # ── States / provinces, scoped to each country ──
    for iso2, state_names in states_by_iso2.items():
        country_id = country_id_by_iso2.get(iso2)
        if not country_id:
            continue
        for state_idx, state_name in enumerate(state_names):
            if not state_name:
                continue
            conn.execute(
                sa.text("""
                    INSERT INTO master_locations (country_id, name, sort_order)
                    VALUES (:country_id, CAST(:name AS VARCHAR), :sort_order)
                    ON CONFLICT (country_id, name) DO NOTHING
                """),
                {"country_id": country_id, "name": state_name, "sort_order": state_idx},
            )


def downgrade() -> None:
    # Data-only seed migration — leave the (now much larger) countries and
    # locations tables in place on downgrade rather than deleting rows that
    # may already be referenced by candidate profiles. The tables themselves
    # are created/dropped by the previous migration.
    pass
