"""convert company profile timestamps from text to datetime

Revision ID: 20260731_company_timestamps
Revises: 20260731_activity_tz
Create Date: 2026-07-31 00:00:00.000000

"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260731_company_timestamps"
down_revision = "20260731_activity_tz"
branch_labels = None
depends_on = None


def _column_type(table_name: str, column_name: str):
    inspector = sa.inspect(op.get_bind())
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return column["type"]
    return None


def _alter_text_timestamp_column(column_name: str) -> None:
    existing_type = _column_type("company_profiles", column_name)
    if existing_type is None or not isinstance(existing_type, sa.String):
        return

    # The legacy baseline created these as TEXT, but the ORM compares them as
    # TIMESTAMP WITHOUT TIME ZONE. Convert parseable values and backfill blanks
    # so dashboard date filters do not compare text against datetime params.
    op.execute(
        sa.text(
            f"""
            UPDATE company_profiles
            SET {column_name} = CURRENT_TIMESTAMP::text
            WHERE NULLIF(BTRIM({column_name}), '') IS NULL
            """
        )
    )
    op.alter_column(
        "company_profiles",
        column_name,
        type_=sa.DateTime(timezone=False),
        existing_type=existing_type,
        existing_nullable=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using=(
            f"""
            CASE
                WHEN {column_name} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                    THEN {column_name}::timestamp
                ELSE CURRENT_TIMESTAMP
            END
            """
        ),
    )


def upgrade() -> None:
    if context.is_offline_mode():
        for column_name in ("created_at", "updated_at"):
            op.execute(
                f"""
                UPDATE company_profiles
                SET {column_name} = CURRENT_TIMESTAMP::text
                WHERE NULLIF(BTRIM({column_name}), '') IS NULL
                """
            )
            op.execute(
                f"""
                ALTER TABLE company_profiles
                ALTER COLUMN {column_name} TYPE TIMESTAMP
                USING CASE
                    WHEN {column_name} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                        THEN {column_name}::timestamp
                    ELSE CURRENT_TIMESTAMP
                END
                """
            )
            op.execute(
                f"""
                ALTER TABLE company_profiles
                ALTER COLUMN {column_name} SET DEFAULT CURRENT_TIMESTAMP
                """
            )
        return

    _alter_text_timestamp_column("created_at")
    _alter_text_timestamp_column("updated_at")


def downgrade() -> None:
    op.alter_column(
        "company_profiles",
        "updated_at",
        type_=sa.Text(),
        existing_type=sa.DateTime(timezone=False),
        existing_nullable=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="updated_at::text",
    )
    op.alter_column(
        "company_profiles",
        "created_at",
        type_=sa.Text(),
        existing_type=sa.DateTime(timezone=False),
        existing_nullable=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at::text",
    )
