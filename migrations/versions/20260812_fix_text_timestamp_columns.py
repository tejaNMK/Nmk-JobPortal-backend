"""fix text timestamp columns

Revision ID: 20260812_fix_text_timestamp_columns
Revises: 20260812_applicant_ranking_cache
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_fix_text_timestamp_columns"
down_revision = "20260812_applicant_ranking_cache"
branch_labels = None
depends_on = None


TIMESTAMP_COLUMNS = (
    ("employer_profiles", "created_at", False, True),
    ("employer_profiles", "updated_at", False, True),
    ("employer_profiles", "deleted_at", True, False),
    ("job_metrics", "last_viewed_at", True, False),
    ("job_metrics", "updated_at", True, True),
    ("shortlisted_candidates", "shortlisted_at", True, True),
)


def _column_type(table_name: str, column_name: str):
    inspector = sa.inspect(op.get_bind())
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return column["type"]
    return None


def _validate_text_timestamps(table_name: str, column_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                bad_value text;
            BEGIN
                SELECT {column_name}
                INTO bad_value
                FROM {table_name}
                WHERE NULLIF(BTRIM({column_name}), '') IS NOT NULL
                  AND NOT (
                    BTRIM({column_name}) ~
                    '^\\d{{4}}-\\d{{2}}-\\d{{2}}([ T]\\d{{2}}:\\d{{2}}(:\\d{{2}}(\\.\\d{{1,6}})?)?)?([zZ]|[+-]\\d{{2}}(:?\\d{{2}})?)?$'
                  )
                LIMIT 1;

                IF bad_value IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Cannot convert %.% to timestamptz; invalid timestamp text: %',
                        '{table_name}',
                        '{column_name}',
                        bad_value;
                END IF;
            END $$;
            """
        )
    )


def _upgrade_column(
    table_name: str,
    column_name: str,
    nullable: bool,
    has_default: bool,
) -> None:
    existing_type = _column_type(table_name, column_name)
    if existing_type is None or not isinstance(existing_type, sa.String):
        return

    _validate_text_timestamps(table_name, column_name)
    op.alter_column(
        table_name,
        column_name,
        existing_type=existing_type,
        type_=sa.DateTime(timezone=True),
        existing_nullable=nullable,
        nullable=nullable,
        existing_server_default=sa.text("CURRENT_TIMESTAMP") if has_default else None,
        server_default=sa.text("CURRENT_TIMESTAMP") if has_default else None,
        postgresql_using=f"NULLIF(BTRIM({column_name}), '')::timestamptz",
    )


def _downgrade_column(
    table_name: str,
    column_name: str,
    nullable: bool,
    has_default: bool,
) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Text(),
        existing_nullable=nullable,
        nullable=nullable,
        existing_server_default=sa.text("CURRENT_TIMESTAMP") if has_default else None,
        server_default=sa.text("CURRENT_TIMESTAMP") if has_default else None,
        postgresql_using=f"{column_name}::text",
    )


def upgrade() -> None:
    for table_name, column_name, nullable, has_default in TIMESTAMP_COLUMNS:
        _upgrade_column(table_name, column_name, nullable, has_default)


def downgrade() -> None:
    for table_name, column_name, nullable, has_default in reversed(TIMESTAMP_COLUMNS):
        _downgrade_column(table_name, column_name, nullable, has_default)
