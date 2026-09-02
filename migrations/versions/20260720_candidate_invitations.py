"""add candidate invitation table

Revision ID: 20260720_candidate_invitations
Revises: 6ab3c4f2d29b
Create Date: 2026-07-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_candidate_invitations"
down_revision = "74c90f3555b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "candidate_invitations",
        sa.Column(
            "invitation_id",
            sa.Text(),
            server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
            nullable=False,
        ),
        sa.Column(
            "employer_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("custom_message", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("invited_at", sa.DateTime(), nullable=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("invitation_id"),
        sa.ForeignKeyConstraint(["employer_id"], ["employer_profiles.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_profiles.candidate_id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
    )

    op.create_index(
        "idx_candidate_invitations_employer",
        "candidate_invitations",
        ["employer_id"],
    )
    op.create_index(
        "idx_candidate_invitations_candidate",
        "candidate_invitations",
        ["candidate_id"],
    )
    op.create_index(
        "idx_candidate_invitations_job",
        "candidate_invitations",
        ["job_id"],
    )
    op.create_index(
        "idx_candidate_invitations_status",
        "candidate_invitations",
        ["status"],
    )
    op.create_index(
        "idx_candidate_invitations_created_at",
        "candidate_invitations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_candidate_invitations_created_at", table_name="candidate_invitations")
    op.drop_index("idx_candidate_invitations_status", table_name="candidate_invitations")
    op.drop_index("idx_candidate_invitations_job", table_name="candidate_invitations")
    op.drop_index("idx_candidate_invitations_candidate", table_name="candidate_invitations")
    op.drop_index("idx_candidate_invitations_employer", table_name="candidate_invitations")
    op.drop_table("candidate_invitations")

