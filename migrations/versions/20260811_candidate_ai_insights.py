"""add candidate ai insights

Revision ID: 20260811_candidate_ai_insights
Revises: 20260807_ai_candidate_matching
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260811_candidate_ai_insights"
down_revision = "20260807_ai_candidate_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_ai_insights",
        sa.Column(
            "insight_id",
            sa.Text(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
        ),
        sa.Column("candidate_id", sa.Text(), sa.ForeignKey("candidate_profiles.candidate_id"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("primary_skills", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("experience_level", sa.String(length=30), nullable=False, server_default=sa.text("'UNKNOWN'")),
        sa.Column("career_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("key_strengths", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("potential_gaps", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("suitable_roles", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notable_experience", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("education_summary", sa.Text(), nullable=True),
        sa.Column("certifications", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("years_of_experience", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=False, server_default=sa.text("'LOW'")),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("candidate_data_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("candidate_id", name="uq_candidate_ai_insights_candidate"),
    )
    op.create_index("idx_candidate_ai_insights_candidate", "candidate_ai_insights", ["candidate_id"])
    op.create_index("idx_candidate_ai_insights_hash", "candidate_ai_insights", ["candidate_data_hash"])
    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
            COALESCE(feature_flags::jsonb, '{}'::jsonb)
            || '{"ai_candidate_insights": true, "ai_candidate_insights_per_month": null}'::jsonb
        )::json
        WHERE upper(subscription_type) = 'EMPLOYER'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
            COALESCE(feature_flags::jsonb, '{}'::jsonb)
            - 'ai_candidate_insights'
            - 'ai_candidate_insights_per_month'
        )::json
        WHERE feature_flags IS NOT NULL
        """
    )
    op.drop_index("idx_candidate_ai_insights_hash", table_name="candidate_ai_insights")
    op.drop_index("idx_candidate_ai_insights_candidate", table_name="candidate_ai_insights")
    op.drop_table("candidate_ai_insights")
