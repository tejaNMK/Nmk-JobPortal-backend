"""master data (country/location/notice period/salary expectation/target
roles) + candidate profile fields (country, CTC)

Revision ID: 9d4f1a6b8c23
Revises: 3c9f2a7e5d16
Create Date: 2026-07-08 00:00:00.000000

"""

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d4f1a6b8c23"
down_revision = "3c9f2a7e5d16"
branch_labels = None
depends_on = None


NOTICE_PERIODS = [
    "Immediate",
    "15 Days",
    "30 Days",
    "45 Days",
    "60 Days",
    "90 Days",
]

SALARY_EXPECTATIONS = [
    "3-5 LPA",
    "5-8 LPA",
    "8-12 LPA",
    "12-18 LPA",
]

# (country name, iso_code, phone_code, [cities...])
COUNTRIES = [
    ("India", "IN", "+91", [
        "Bengaluru", "Mumbai", "Delhi NCR", "Hyderabad", "Pune",
        "Chennai", "Kolkata", "Ahmedabad", "Remote",
    ]),
    ("United States", "US", "+1", [
        "New York", "San Francisco", "Austin", "Seattle", "Chicago",
        "Boston", "Remote",
    ]),
    ("United Kingdom", "GB", "+44", [
        "London", "Manchester", "Birmingham", "Edinburgh", "Remote",
    ]),
    ("Canada", "CA", "+1", [
        "Toronto", "Vancouver", "Montreal", "Ottawa", "Remote",
    ]),
    ("Australia", "AU", "+61", [
        "Sydney", "Melbourne", "Brisbane", "Perth", "Remote",
    ]),
    ("Germany", "DE", "+49", [
        "Berlin", "Munich", "Frankfurt", "Hamburg", "Remote",
    ]),
    ("Singapore", "SG", "+65", [
        "Singapore", "Remote",
    ]),
    ("United Arab Emirates", "AE", "+971", [
        "Dubai", "Abu Dhabi", "Sharjah", "Remote",
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


def _seed_data_offline() -> None:
    for idx, label in enumerate(NOTICE_PERIODS):
        op.execute(
            "INSERT INTO master_notice_periods (label, sort_order) "
            f"VALUES ({_sql_literal(label)}, {idx}) "
            "ON CONFLICT (label) DO NOTHING"
        )

    for idx, label in enumerate(SALARY_EXPECTATIONS):
        op.execute(
            "INSERT INTO master_salary_expectations (label, sort_order) "
            f"VALUES ({_sql_literal(label)}, {idx}) "
            "ON CONFLICT (label) DO NOTHING"
        )

    for idx, (country_name, iso_code, phone_code, cities) in enumerate(COUNTRIES):
        op.execute(
            "INSERT INTO master_countries (name, iso_code, phone_code, sort_order) "
            f"VALUES ({_sql_literal(country_name)}, {_sql_literal(iso_code)}, "
            f"{_sql_literal(phone_code)}, {idx}) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name"
        )

        for city_idx, city in enumerate(cities):
            op.execute(
                "INSERT INTO master_locations (country_id, name, sort_order) "
                f"SELECT country_id, CAST({_sql_literal(city)} AS VARCHAR), {city_idx} "
                "FROM master_countries "
                f"WHERE name = {_sql_literal(country_name)} "
                "ON CONFLICT (country_id, name) DO NOTHING"
            )

    _seed_target_roles_offline()


def _seed_target_roles_offline() -> None:
    for name in SEED_TARGET_ROLES:
        op.execute(
            "INSERT INTO master_target_roles (name) "
            f"VALUES ({_sql_literal(name)}) "
            "ON CONFLICT (name) DO NOTHING"
        )


SEED_TARGET_ROLES = [
    "Software Engineer", "Senior Software Engineer", "Product Manager",
    "Product Designer", "UX Designer", "Data Analyst", "Data Scientist",
    "DevOps Engineer", "QA Engineer", "Engineering Manager",
    "Business Analyst", "HR Manager", "Sales Executive",
    "Marketing Manager", "Customer Success Manager",
]


def upgrade() -> None:

    # =====================================================
    # master_countries
    # =====================================================
    op.create_table(
        "master_countries",
        sa.Column("country_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("iso_code", sa.String(length=3), nullable=True),
        sa.Column("phone_code", sa.String(length=10), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("country_id"),
    )
    op.create_index("idx_master_countries_name", "master_countries", ["name"], unique=True)

    # =====================================================
    # master_locations
    # =====================================================
    op.create_table(
        "master_locations",
        sa.Column("location_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("country_id", sa.Text(), sa.ForeignKey("master_countries.country_id"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("location_id"),
    )
    op.create_index("idx_master_locations_country", "master_locations", ["country_id"], unique=False)
    op.create_index(
        "idx_master_locations_country_name",
        "master_locations",
        ["country_id", "name"],
        unique=True,
    )

    # =====================================================
    # master_notice_periods
    # =====================================================
    op.create_table(
        "master_notice_periods",
        sa.Column("notice_period_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("notice_period_id"),
    )
    op.create_index("idx_master_notice_periods_label", "master_notice_periods", ["label"], unique=True)

    # =====================================================
    # master_salary_expectations
    # =====================================================
    op.create_table(
        "master_salary_expectations",
        sa.Column("salary_expectation_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("label", sa.String(length=150), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("salary_expectation_id"),
    )
    op.create_index("idx_master_salary_expectations_label", "master_salary_expectations", ["label"], unique=True)

    # =====================================================
    # master_target_roles
    # =====================================================
    op.create_table(
        "master_target_roles",
        sa.Column("target_role_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("target_role_id"),
    )
    op.create_index("idx_master_target_roles_name", "master_target_roles", ["name"], unique=True)

    # =====================================================
    # candidate_target_roles (candidate <-> target role, many-to-many)
    # =====================================================
    op.create_table(
        "candidate_target_roles",
        sa.Column("candidate_target_role_id", sa.Text(), nullable=False,
                  server_default=sa.text("replace(gen_random_uuid()::text, '-', '')")),
        sa.Column("candidate_id", sa.Text(), sa.ForeignKey("candidate_profiles.candidate_id"), nullable=False),
        sa.Column("target_role_id", sa.Text(), sa.ForeignKey("master_target_roles.target_role_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("candidate_target_role_id"),
    )
    op.create_index("idx_candidate_target_roles_candidate", "candidate_target_roles", ["candidate_id"], unique=False)
    op.create_index(
        "idx_candidate_target_roles_unique",
        "candidate_target_roles",
        ["candidate_id", "target_role_id"],
        unique=True,
    )

    # =====================================================
    # candidate_profiles - new columns
    # =====================================================
    op.execute("""
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS country_id TEXT REFERENCES master_countries(country_id),
        ADD COLUMN IF NOT EXISTS primary_location_id TEXT REFERENCES master_locations(location_id),
        ADD COLUMN IF NOT EXISTS preferred_location_id TEXT REFERENCES master_locations(location_id),
        ADD COLUMN IF NOT EXISTS notice_period_id TEXT REFERENCES master_notice_periods(notice_period_id),
        ADD COLUMN IF NOT EXISTS salary_expectation_id TEXT REFERENCES master_salary_expectations(salary_expectation_id),
        ADD COLUMN IF NOT EXISTS current_ctc NUMERIC(12, 2),
        ADD COLUMN IF NOT EXISTS expected_ctc NUMERIC(12, 2)
    """)

    # =====================================================
    # Seed data
    # =====================================================
    if context.is_offline_mode():
        _seed_data_offline()
        return

    conn = op.get_bind()

    for label in NOTICE_PERIODS:
        conn.execute(
            sa.text("""
                INSERT INTO master_notice_periods (label, sort_order)
                VALUES (:label, :sort_order)
                ON CONFLICT (label) DO NOTHING
            """),
            {"label": label, "sort_order": NOTICE_PERIODS.index(label)},
        )

    for label in SALARY_EXPECTATIONS:
        conn.execute(
            sa.text("""
                INSERT INTO master_salary_expectations (label, sort_order)
                VALUES (:label, :sort_order)
                ON CONFLICT (label) DO NOTHING
            """),
            {"label": label, "sort_order": SALARY_EXPECTATIONS.index(label)},
        )

    for idx, (country_name, iso_code, phone_code, cities) in enumerate(COUNTRIES):
        result = conn.execute(
            sa.text("""
                INSERT INTO master_countries (name, iso_code, phone_code, sort_order)
                VALUES (:name, :iso_code, :phone_code, :sort_order)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING country_id
            """),
            {"name": country_name, "iso_code": iso_code, "phone_code": phone_code, "sort_order": idx},
        )
        country_id = result.scalar_one()

        for city_idx, city in enumerate(cities):
            conn.execute(
                sa.text("""
                    INSERT INTO master_locations (country_id, name, sort_order)
                    VALUES (:country_id, CAST(:name AS VARCHAR), :sort_order)
                    ON CONFLICT (country_id, name) DO NOTHING
                """),
                {"country_id": country_id, "name": city, "sort_order": city_idx},
            )

    for name in SEED_TARGET_ROLES:
        conn.execute(
            sa.text("""
                INSERT INTO master_target_roles (name)
                VALUES (:name)
                ON CONFLICT (name) DO NOTHING
            """),
            {"name": name},
        )


def downgrade() -> None:

    op.execute("""
        ALTER TABLE candidate_profiles
        DROP COLUMN IF EXISTS country_id,
        DROP COLUMN IF EXISTS primary_location_id,
        DROP COLUMN IF EXISTS preferred_location_id,
        DROP COLUMN IF EXISTS notice_period_id,
        DROP COLUMN IF EXISTS salary_expectation_id,
        DROP COLUMN IF EXISTS current_ctc,
        DROP COLUMN IF EXISTS expected_ctc
    """)

    op.drop_index("idx_candidate_target_roles_unique", table_name="candidate_target_roles")
    op.drop_index("idx_candidate_target_roles_candidate", table_name="candidate_target_roles")
    op.drop_table("candidate_target_roles")

    op.drop_index("idx_master_target_roles_name", table_name="master_target_roles")
    op.drop_table("master_target_roles")

    op.drop_index("idx_master_salary_expectations_label", table_name="master_salary_expectations")
    op.drop_table("master_salary_expectations")

    op.drop_index("idx_master_notice_periods_label", table_name="master_notice_periods")
    op.drop_table("master_notice_periods")

    op.drop_index("idx_master_locations_country_name", table_name="master_locations")
    op.drop_index("idx_master_locations_country", table_name="master_locations")
    op.drop_table("master_locations")

    op.drop_index("idx_master_countries_name", table_name="master_countries")
    op.drop_table("master_countries")
