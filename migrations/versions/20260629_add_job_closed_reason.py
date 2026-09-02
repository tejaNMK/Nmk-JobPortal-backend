"""add closed reason to jobs

Revision ID: 20260629_add_job_closed_reason
Revises: 1bb3e90ae8cd
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6e2f9c4a1b83"
down_revision = "95e547b4302d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("closed_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "closed_reason")
