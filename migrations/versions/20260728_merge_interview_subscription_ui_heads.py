"""merge interview and subscription ui migration heads

Revision ID: 20260728_merge_interview_sub_ui
Revises: 20260728_merge_sub_interview, 20260728_subscription_ui
Create Date: 2026-07-28 00:00:00.000000

"""


revision = "20260728_merge_interview_sub_ui"
down_revision = (
    "20260728_merge_sub_interview",
    "20260728_subscription_ui",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
