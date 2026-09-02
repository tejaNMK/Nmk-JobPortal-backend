

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "74c90f3555b7"
down_revision = "6ab3c4f2d29b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidate_resumes", sa.Column("file_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "idx_candidate_resumes_candidate_file_hash",
        "candidate_resumes",
        ["candidate_id", "file_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_candidate_resumes_candidate_file_hash", table_name="candidate_resumes")
    op.drop_column("candidate_resumes", "file_hash")