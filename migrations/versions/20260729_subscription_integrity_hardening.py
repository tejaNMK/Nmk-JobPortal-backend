"""harden subscription integrity constraints

Revision ID: 20260729_subscription_integrity
Revises: 20260729_job_structured_location
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_subscription_integrity"
down_revision = "20260729_job_structured_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                user_subscription_id,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, UPPER(role)
                    ORDER BY created_at DESC, user_subscription_id DESC
                ) AS rn
            FROM user_subscriptions
            WHERE status = 'ACTIVE'
        )
        UPDATE user_subscriptions AS us
        SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP
        FROM ranked
        WHERE us.user_subscription_id = ranked.user_subscription_id
          AND ranked.rn > 1
        """
    )
    op.drop_index("uq_user_subscriptions_one_active", table_name="user_subscriptions")
    op.create_index(
        "uq_user_subscriptions_one_active_role",
        "user_subscriptions",
        ["user_id", sa.text("UPPER(role)")],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_check_constraint(
        "ck_subscriptions_price_non_negative",
        "subscriptions",
        "price >= 0",
    )
    op.create_check_constraint(
        "ck_subscriptions_duration_positive",
        "subscriptions",
        "duration_days > 0",
    )
    op.create_check_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        """
        (max_job_posts IS NULL OR max_job_posts >= 0)
        AND (max_job_alerts IS NULL OR max_job_alerts >= 0)
        AND (max_resume_uploads IS NULL OR max_resume_uploads >= 0)
        AND (max_candidate_searches IS NULL OR max_candidate_searches >= 0)
        """,
    )
    op.create_check_constraint(
        "ck_user_subscriptions_status",
        "user_subscriptions",
        "status IN ('ACTIVE', 'CANCELLED', 'EXPIRED', 'PENDING', 'SUSPENDED', 'PAYMENT_FAILED', 'REFUNDED')",
    )
    op.create_check_constraint(
        "ck_user_subscriptions_payment_status",
        "user_subscriptions",
        "payment_status IN ('FREE', 'PAID', 'PENDING', 'FAILED', 'REFUNDED')",
    )
    op.create_check_constraint(
        "ck_user_subscriptions_amounts_non_negative",
        "user_subscriptions",
        "price_paid >= 0 AND discount_amount >= 0",
    )
    op.create_check_constraint(
        "ck_user_subscriptions_date_range",
        "user_subscriptions",
        "end_date > start_date",
    )
    op.create_check_constraint(
        "ck_subscription_usage_used_count_non_negative",
        "subscription_usage",
        "used_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_subscription_usage_used_count_non_negative",
        "subscription_usage",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_subscriptions_date_range",
        "user_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_subscriptions_amounts_non_negative",
        "user_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_subscriptions_payment_status",
        "user_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_subscriptions_status",
        "user_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_limits_non_negative",
        "subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_duration_positive",
        "subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_subscriptions_price_non_negative",
        "subscriptions",
        type_="check",
    )
    op.drop_index(
        "uq_user_subscriptions_one_active_role",
        table_name="user_subscriptions",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_user_subscriptions_one_active",
        "user_subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
