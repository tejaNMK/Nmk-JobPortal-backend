"""merge razorpay payment fields with active job soft-delete indexes

Revision ID: 20260817_merge_razorpay_active_jobs
Revises: 20260817_razorpay_subscription_fields, 20260807_active_job_soft_delete_indexes
Create Date: 2026-08-17
"""


revision = "20260817_merge_razorpay_active_jobs"
down_revision = (
    "20260817_razorpay_subscription_fields",
    "20260807_active_job_soft_delete_indexes",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
