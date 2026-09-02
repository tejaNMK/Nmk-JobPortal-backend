"""complete schema baseline repair

Revision ID: 1f0a2b3c4d5e
Revises: d3b8f6a1c947
Create Date: 2026-07-01 00:00:00.000000

"""

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "1f0a2b3c4d5e"
down_revision = "d3b8f6a1c947"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    if context.is_offline_mode():
        return

    if not _has_table("person"):
        op.create_table(
            "person",
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("application_notes"):
        op.create_table(
            "application_notes",
            sa.Column(
                "note_id",
                sa.Text(),
                server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
                nullable=False,
            ),
            sa.Column("application_id", sa.Text(), nullable=False),
            sa.Column("note_text", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=True,
            ),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["application_id"],
                ["job_applications.application_id"],
            ),
            sa.PrimaryKeyConstraint("note_id"),
        )


def downgrade() -> None:
    if context.is_offline_mode():
        return

    if _has_table("application_notes"):
        op.drop_table("application_notes")

    if _has_table("person"):
        op.drop_table("person")
