"""add applicant ranking cache fields

Revision ID: 20260812_applicant_ranking_cache
Revises: 20260811_candidate_ai_insights
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_applicant_ranking_cache"
down_revision = "20260811_candidate_ai_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_recommendations",
        sa.Column("application_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("deterministic_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("semantic_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("match_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("match_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("missing_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("job_updated_at_snapshot", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("candidate_updated_at_snapshot", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "candidate_recommendations",
        sa.Column("resume_detail_generated_at_snapshot", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidate_recommendations_application",
        "candidate_recommendations",
        "job_applications",
        ["application_id"],
        ["application_id"],
    )
    op.create_index(
        "idx_candidate_recommendations_job_candidate",
        "candidate_recommendations",
        ["job_id", "candidate_id"],
    )
    op.create_index(
        "idx_candidate_recommendations_application",
        "candidate_recommendations",
        ["application_id"],
    )
    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
            COALESCE(feature_flags, '{}'::json)::jsonb
            || '{"ai_applicant_ranking": false}'::jsonb
        )::json
        WHERE upper(subscription_type) = 'EMPLOYER'
          AND NOT (COALESCE(feature_flags, '{}'::json)::jsonb ? 'ai_applicant_ranking')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
            COALESCE(feature_flags, '{}'::json)::jsonb - 'ai_applicant_ranking'
        )::json
        WHERE upper(subscription_type) = 'EMPLOYER'
        """
    )
    op.drop_index(
        "idx_candidate_recommendations_application",
        table_name="candidate_recommendations",
    )
    op.drop_index(
        "idx_candidate_recommendations_job_candidate",
        table_name="candidate_recommendations",
    )
    op.drop_constraint(
        "fk_candidate_recommendations_application",
        "candidate_recommendations",
        type_="foreignkey",
    )
    op.drop_column("candidate_recommendations", "resume_detail_generated_at_snapshot")
    op.drop_column("candidate_recommendations", "candidate_updated_at_snapshot")
    op.drop_column("candidate_recommendations", "job_updated_at_snapshot")
    op.drop_column("candidate_recommendations", "score_breakdown")
    op.drop_column("candidate_recommendations", "missing_requirements")
    op.drop_column("candidate_recommendations", "match_reasons")
    op.drop_column("candidate_recommendations", "match_label")
    op.drop_column("candidate_recommendations", "semantic_score")
    op.drop_column("candidate_recommendations", "deterministic_score")
    op.drop_column("candidate_recommendations", "application_id")
