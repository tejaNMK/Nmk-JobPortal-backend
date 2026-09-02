"""role default subscription settings

Revision ID: 20260728_role_default_settings
Revises: 20260728_merge_interview_sub_ui
Create Date: 2026-07-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_role_default_settings"
down_revision = "20260728_merge_interview_sub_ui"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "candidate_default_subscription_plan",
            sa.String(length=150),
            nullable=True,
        ),
    )
    op.add_column(
        "system_settings",
        sa.Column(
            "employer_default_subscription_plan",
            sa.String(length=150),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE system_settings settings
        SET candidate_default_subscription_plan = settings.default_subscription_plan
        FROM subscriptions subscriptions
        WHERE settings.default_subscription_plan = subscriptions.subscription_id::text
          AND upper(subscriptions.subscription_type) = 'CANDIDATE'
        """
    )
    op.execute(
        """
        UPDATE system_settings settings
        SET employer_default_subscription_plan = settings.default_subscription_plan
        FROM subscriptions subscriptions
        WHERE settings.default_subscription_plan = subscriptions.subscription_id::text
          AND upper(subscriptions.subscription_type) = 'EMPLOYER'
        """
    )


def downgrade() -> None:
    op.drop_column("system_settings", "employer_default_subscription_plan")
    op.drop_column("system_settings", "candidate_default_subscription_plan")
