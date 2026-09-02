"""subscription api integrity hardening

Revision ID: 20260801_sub_api_integrity
Revises: 20260731_remove_unused_sub_features
Create Date: 2026-08-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_sub_api_integrity"
down_revision = "20260731_remove_unused_sub_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                subscription_id,
                ROW_NUMBER() OVER (
                    PARTITION BY lower(subscription_name)
                    ORDER BY created_at ASC, subscription_id ASC
                ) AS rn
            FROM subscriptions
        )
        UPDATE subscriptions AS s
        SET subscription_name = s.subscription_name || ' (' || ranked.rn || ')',
            updated_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE s.subscription_id = ranked.subscription_id
          AND ranked.rn > 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                subscription_id,
                ROW_NUMBER() OVER (
                    PARTITION BY upper(subscription_type)
                    ORDER BY updated_at DESC, created_at DESC, subscription_id DESC
                ) AS rn
            FROM subscriptions
            WHERE is_default = true
              AND is_active = true
        )
        UPDATE subscriptions AS s
        SET is_default = false,
            updated_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE s.subscription_id = ranked.subscription_id
          AND ranked.rn > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_subscriptions_name_lower "
        "ON subscriptions (lower(subscription_name))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_subscriptions_one_active_default_type "
        "ON subscriptions (upper(subscription_type)) "
        "WHERE is_default = true AND is_active = true"
    )
    op.create_check_constraint(
        "ck_subscriptions_type",
        "subscriptions",
        "subscription_type IN ('CANDIDATE', 'EMPLOYER', 'ADMIN')",
    )
    op.create_check_constraint(
        "ck_user_subscriptions_role",
        "user_subscriptions",
        "role IN ('CANDIDATE', 'EMPLOYER', 'ADMIN')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_subscriptions_role",
        "user_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_type",
        "subscriptions",
        type_="check",
    )
    op.drop_index(
        "uq_subscriptions_one_active_default_type",
        table_name="subscriptions",
    )
    op.drop_index(
        "uq_subscriptions_name_lower",
        table_name="subscriptions",
    )
