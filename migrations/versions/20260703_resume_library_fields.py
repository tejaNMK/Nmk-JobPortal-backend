"""add resume library fields (versions, archive, share links)

Revision ID: 3c9f2a7e5d16
Revises: 7a2c5e9f1b34
Create Date: 2026-07-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3c9f2a7e5d16"
down_revision = "b6e4d8a0c912"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidate_resumes", sa.Column("version_name", sa.Text(), nullable=True))
    op.add_column("candidate_resumes", sa.Column("template", sa.Text(), server_default="Minimal ATS", nullable=True))
    op.add_column("candidate_resumes", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("candidate_resumes", sa.Column("usage_note", sa.Text(), nullable=True))
    op.add_column("candidate_resumes", sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("candidate_resumes", sa.Column("download_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("candidate_resumes", sa.Column("share_token", sa.Text(), nullable=True))
    op.add_column("candidate_resumes", sa.Column("share_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("candidate_resumes", sa.Column("share_requires_email", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("candidate_resumes", sa.Column("share_expires_at", sa.DateTime(), nullable=True))
    op.add_column("candidate_resumes", sa.Column("share_view_count", sa.Integer(), server_default=sa.text("0"), nullable=False))

    op.create_unique_constraint("uq_candidate_resumes_share_token", "candidate_resumes", ["share_token"])

    # Backfill a sensible display name for any rows created before this
    # migration so the Resume Library UI never shows a blank name.
    op.execute(
        "UPDATE candidate_resumes SET version_name = COALESCE(version_name, file_name, 'Resume') "
        "WHERE version_name IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("uq_candidate_resumes_share_token", "candidate_resumes", type_="unique")
    op.drop_column("candidate_resumes", "share_view_count")
    op.drop_column("candidate_resumes", "share_expires_at")
    op.drop_column("candidate_resumes", "share_requires_email")
    op.drop_column("candidate_resumes", "share_enabled")
    op.drop_column("candidate_resumes", "share_token")
    op.drop_column("candidate_resumes", "download_count")
    op.drop_column("candidate_resumes", "is_archived")
    op.drop_column("candidate_resumes", "usage_note")
    op.drop_column("candidate_resumes", "notes")
    op.drop_column("candidate_resumes", "template")
    op.drop_column("candidate_resumes", "version_name")
