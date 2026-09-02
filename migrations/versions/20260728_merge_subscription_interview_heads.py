"""merge subscription and interview migration heads

Revision ID: 20260728_merge_sub_interview
Revises: 20260727_subscription_defaults, 20260728_interview_rounds
Create Date: 2026-07-28 00:00:00.000000

"""


revision = "20260728_merge_sub_interview"
down_revision = (
    "20260727_subscription_defaults",
    "20260728_interview_rounds",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
