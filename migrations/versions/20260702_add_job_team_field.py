"""add team field to jobs

Revision ID: 7a2c5e9f1b34
Revises: 1f0a2b3c4d5e
Create Date: 2026-07-02 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a2c5e9f1b34"
down_revision = "1f0a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("team", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "team")