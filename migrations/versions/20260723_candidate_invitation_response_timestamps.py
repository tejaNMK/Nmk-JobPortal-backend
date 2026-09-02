"""add candidate invitation response timestamps

Revision ID: 20260723_invite_resp_times
Revises: 20260720_candidate_invitations
Create Date: 2026-07-23

"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_invite_resp_times"
down_revision = "20260720_candidate_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_invitations",
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "candidate_invitations",
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_invitations", "rejected_at")
    op.drop_column("candidate_invitations", "accepted_at")
