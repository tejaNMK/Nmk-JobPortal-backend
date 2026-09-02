"""create email verification tokens table

Revision ID: 20260624_email_verification_tokens
Revises: 20260623_job_application_shortlist_fields
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "email_verification_otp"
down_revision = "add_user_job_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_verification_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column(
            "is_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_evt_email_expires_at",
        "email_verification_tokens",
        ["email", "expires_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_evt_email_expires_at", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

