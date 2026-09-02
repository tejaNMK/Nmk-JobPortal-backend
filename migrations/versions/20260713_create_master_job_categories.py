"""create master job categories

Revision ID: c4d8e1f7a921
Revises: b7e2c4a9f103
Create Date: 2026-07-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "c4d8e1f7a921"
down_revision = "20260713_profiles"
branch_labels = None
depends_on = None


JOB_CATEGORIES = [
    "Information Technology",
    "Engineering",
    "Finance",
    "Human Resources",
    "Marketing",
    "Sales",
    "Operations",
    "Customer Support",
    "Healthcare",
    "Legal",
]


def upgrade() -> None:
    op.create_table(
        "master_job_categories",
        sa.Column(
            "job_category_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text(
                "replace(gen_random_uuid()::text, '-', '')"
            ),
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("job_category_id"),
    )

    op.create_index(
        "idx_master_job_categories_name",
        "master_job_categories",
        ["name"],
        unique=True,
    )

    conn = op.get_bind()

    for idx, name in enumerate(JOB_CATEGORIES):
        conn.execute(
            sa.text(
                """
                INSERT INTO master_job_categories
                    (name, sort_order)
                VALUES
                    (:name, :sort_order)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {
                "name": name,
                "sort_order": idx,
            },
        )


def downgrade() -> None:
    op.drop_index(
        "idx_master_job_categories_name",
        table_name="master_job_categories",
    )

    op.drop_table("master_job_categories")