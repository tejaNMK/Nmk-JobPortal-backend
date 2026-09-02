"""add candidate_resumes.file_size

QA bug: "Download CV: UI should display file size before download". The
Download CV page already renders a file-size string in each resume row's
meta line (see DownloadCvPage.jsx's formatFileSize helper), but the backend
never captured or returned a file size, so it always came back missing and
the UI silently omitted it.

This migration adds a nullable `file_size` column (bytes) to
candidate_resumes. It's populated going forward at upload time
(CandidateProfileService.upload_resume_file) and copied over when a resume
version is duplicated. Existing rows uploaded before this change are
backfilled to NULL (unknown) rather than guessed at -- the frontend already
treats a missing value as "omit the size" rather than showing "0 Bytes".

Revision ID: f2b6c1d9a834
Revises: e1a4f2c8b715
Create Date: 2026-07-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2b6c1d9a834"
down_revision = "e1a4f2c8b715"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidate_resumes", sa.Column("file_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidate_resumes", "file_size")