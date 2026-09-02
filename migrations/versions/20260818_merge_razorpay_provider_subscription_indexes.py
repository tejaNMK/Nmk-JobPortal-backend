"""merge razorpay provider uniqueness with subscription lookup indexes

Revision ID: 20260818_merge_razorpay_provider_subscription_indexes
Revises: 20260811_razorpay_provider_id_uniqueness, 20260817_current_subscription_lookup_indexes
Create Date: 2026-08-18
"""


revision = "20260818_merge_razorpay_provider_subscription_indexes"
down_revision = (
    "20260811_razorpay_provider_id_uniqueness",
    "20260817_current_subscription_lookup_indexes",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
