"""fix candidate_resumes.template incorrect default

The "template" column was given a server_default of 'Minimal ATS' when it
was added. That's wrong: template is a label the candidate chooses for a
resume version (via the Manage Resume "Version Controls" form); it should
be NULL until they actually pick one. Because of the bad default, every
uploaded resume (PDF/DOCX) silently got "Minimal ATS" stamped on it, which
the Download CV page then displayed as "Template: Minimal ATS" for every
non-default resume version — see QA bug "Displaying Template: Minimal ATS
for non default resumes".

This migration:
1. Drops the server-side default so newly inserted rows leave template NULL
   unless explicitly set.
2. Backfills existing rows: any resume whose template is still the
   untouched default value 'Minimal ATS' is reset to NULL. (Rows where a
   candidate explicitly re-selected "Minimal ATS" via the template dropdown
   are indistinguishable from the bad default, but doing so was never
   actually possible before this fix ships, since the UI only reads/writes
   this column and the column always came back as 'Minimal ATS' — so it is
   safe to treat every current 'Minimal ATS' value as the unintended
   default.)

Revision ID: e1a4f2c8b715
Revises: b7e2c4a9f103
Create Date: 2026-07-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1a4f2c8b715"
down_revision = "b7e2c4a9f103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "candidate_resumes",
        "template",
        existing_type=sa.Text(),
        server_default=None,
        nullable=True,
    )
    op.execute(
        "UPDATE candidate_resumes SET template = NULL WHERE template = 'Minimal ATS'"
    )


def downgrade() -> None:
    op.alter_column(
        "candidate_resumes",
        "template",
        existing_type=sa.Text(),
        server_default="Minimal ATS",
        nullable=True,
    )