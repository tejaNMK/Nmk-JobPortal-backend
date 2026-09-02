"""merge payment jobs head with candidate ai insights

Revision ID: 20260817_merge_payment_candidate_ai
Revises: 20260817_merge_razorpay_active_jobs, 20260811_candidate_ai_insights
Create Date: 2026-08-17
"""


revision = "20260817_merge_payment_candidate_ai"
down_revision = (
    "20260817_merge_razorpay_active_jobs",
    "20260811_candidate_ai_insights",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
