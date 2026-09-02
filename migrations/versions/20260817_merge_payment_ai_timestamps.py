"""merge payment ai head with timestamp column fixes

Revision ID: 20260817_merge_payment_ai_timestamps
Revises: 20260817_merge_payment_candidate_ai, 20260812_fix_text_timestamp_columns
Create Date: 2026-08-17
"""


revision = "20260817_merge_payment_ai_timestamps"
down_revision = (
    "20260817_merge_payment_candidate_ai",
    "20260812_fix_text_timestamp_columns",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
