"""add ai candidate matching

Revision ID: 20260807_ai_candidate_matching
Revises: 20260807_ai_job_description_usage
Create Date: 2026-08-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260807_ai_candidate_matching"
down_revision = "20260807_ai_job_description_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_candidate_matches",
        sa.Column(
            "match_id",
            sa.Text(),
            primary_key=True,
            nullable=False,
            server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
        ),
        sa.Column("job_id", sa.Text(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column("candidate_id", sa.Text(), sa.ForeignKey("candidate_profiles.candidate_id"), nullable=False),
        sa.Column("application_id", sa.Text(), sa.ForeignKey("job_applications.application_id"), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default=sa.text("'AI Recommended Candidate'")),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("skills_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("experience_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("title_domain_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("education_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("location_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("preferred_skills_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("semantic_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("matched_skills", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("missing_required_skills", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("matched_preferred_skills", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("strengths", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("gaps", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("hard_requirements", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("preferred_requirements", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("semantic_signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.String(length=40), nullable=False, server_default=sa.text("'Review Manually'")),
        sa.Column("scoring_version", sa.String(length=40), nullable=False),
        sa.Column("job_updated_at", sa.DateTime(), nullable=True),
        sa.Column("candidate_updated_at", sa.DateTime(), nullable=True),
        sa.Column("resume_generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_ai_candidate_matches_job_candidate"),
    )
    op.create_index("idx_ai_candidate_matches_job_score", "ai_candidate_matches", ["job_id", "overall_score"])
    op.create_index("idx_ai_candidate_matches_candidate", "ai_candidate_matches", ["candidate_id"])
    op.create_index("idx_ai_candidate_matches_source", "ai_candidate_matches", ["source_type"])

    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
            COALESCE(feature_flags::jsonb, '{}'::jsonb)
            || '{"ai_candidate_matching": true, "ai_candidate_matching_runs_per_month": null, "ai_candidate_analyses_per_month": null}'::jsonb
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
            - 'ai_candidate_matching'
            - 'ai_candidate_matching_runs_per_month'
            - 'ai_candidate_analyses_per_month'
        )::json
        WHERE feature_flags IS NOT NULL
        """
    )
    op.drop_index("idx_ai_candidate_matches_source", table_name="ai_candidate_matches")
    op.drop_index("idx_ai_candidate_matches_candidate", table_name="ai_candidate_matches")
    op.drop_index("idx_ai_candidate_matches_job_score", table_name="ai_candidate_matches")
    op.drop_table("ai_candidate_matches")
