"""add interview interviewer assignments

Revision ID: b6e4d8a0c912
Revises: a9c3e2d7f604
Create Date: 2026-07-06 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b6e4d8a0c912"
down_revision = "a9c3e2d7f604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_interviewers",
        sa.Column(
            "interview_interviewer_id",
            sa.Text(),
            server_default=sa.text(
                "replace(gen_random_uuid()::text, '-', '')"
            ),
            nullable=False,
        ),
        sa.Column("interview_id", sa.Text(), nullable=False),
        sa.Column(
            "interviewer_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("assigned_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.interview_id"],
        ),
        sa.ForeignKeyConstraint(
            ["interviewer_user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("interview_interviewer_id"),
    )
    op.create_index(
        "idx_interview_interviewers_interview_id",
        "interview_interviewers",
        ["interview_id"],
    )
    op.create_index(
        "idx_interview_interviewers_user_id",
        "interview_interviewers",
        ["interviewer_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_interview_interviewers_user_id",
        table_name="interview_interviewers",
    )
    op.drop_index(
        "idx_interview_interviewers_interview_id",
        table_name="interview_interviewers",
    )
    op.drop_table("interview_interviewers")
