"""add weekly subscription usage periods

Revision ID: 20260804_weekly_sub_usage
Revises: 20260802_emp_contact_verify
Create Date: 2026-08-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_weekly_sub_usage"
down_revision = "20260802_emp_contact_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_usage",
        sa.Column(
            "period_start",
            sa.DateTime(),
            server_default=sa.text("'1970-01-01 00:00:00'"),
            nullable=False,
        ),
    )
    op.add_column(
        "subscription_usage",
        sa.Column(
            "period_end",
            sa.DateTime(),
            server_default=sa.text("'9999-12-31 23:59:59'"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        "uq_subscription_usage_feature",
        "subscription_usage",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_subscription_usage_feature",
        "subscription_usage",
        ["user_subscription_id", "feature_name", "period_start", "period_end"],
    )
    op.execute(
        """
        UPDATE subscriptions
        SET feature_flags = (
                COALESCE(feature_flags::jsonb, '{}'::jsonb)
                || '{"candidate_invitations_per_week": null}'::jsonb
            )::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE upper(subscription_type) = 'EMPLOYER'
          AND NOT (COALESCE(feature_flags::jsonb, '{}'::jsonb) ? 'candidate_invitations_per_week')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM subscription_usage
        WHERE period_start <> '1970-01-01 00:00:00'
           OR period_end <> '9999-12-31 23:59:59'
        """
    )
    op.drop_constraint(
        "uq_subscription_usage_feature",
        "subscription_usage",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_subscription_usage_feature",
        "subscription_usage",
        ["user_subscription_id", "feature_name"],
    )
    op.drop_column("subscription_usage", "period_end")
    op.drop_column("subscription_usage", "period_start")
