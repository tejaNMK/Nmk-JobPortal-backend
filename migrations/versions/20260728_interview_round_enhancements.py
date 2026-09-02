"""add interview round scheduling fields

Revision ID: 20260728_interview_rounds
Revises: b6e4d8a0c912
Create Date: 2026-07-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_interview_rounds"
down_revision = "b6e4d8a0c912"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("interview_title", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("round_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("end_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("timezone", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "timezone")
    op.drop_column("interviews", "end_time")
    op.drop_column("interviews", "round_number")
    op.drop_column("interviews", "interview_title")
