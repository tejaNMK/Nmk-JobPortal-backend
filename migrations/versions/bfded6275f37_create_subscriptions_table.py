"""create subscriptions table

Revision ID: bfded6275f37
Revises: 5fb5b0df4f9a
Create Date: 2026-07-22 16:49:58.710651

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "bfded6275f37"
down_revision = "5fb5b0df4f9a"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "subscriptions",

        sa.Column(
            "subscription_id",
            sa.UUID(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "subscription_name",
            sa.String(150),
            nullable=False,
        ),

        sa.Column(
            "subscription_type",
            sa.String(30),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "price",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),

        sa.Column(
            "currency",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'INR'"),
        ),

        sa.Column(
            "duration_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),

        sa.Column(
            "max_job_posts",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "max_job_alerts",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "max_resume_uploads",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "max_candidate_searches",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "is_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),

        sa.Column(
            "created_by",
            sa.UUID(),
            nullable=True,
        ),

        sa.Column(
            "updated_by",
            sa.UUID(),
            nullable=True,
        ),
    )


def downgrade() -> None:

    op.drop_table("subscriptions")