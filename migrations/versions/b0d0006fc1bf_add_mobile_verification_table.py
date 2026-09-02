"""add mobile verification table

Revision ID: b0d0006fc1bf
Revises: 20260623_job_application_fields
Create Date: 2026-06-24 13:12:36.486395

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b0d0006fc1bf"
down_revision = "email_verification_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "mobile_verifications",

        sa.Column(
            "verification_id",
            sa.Text(),
            nullable=False
        ),

        sa.Column(
            "country_code",
            sa.String(length=10),
            nullable=False
        ),

        sa.Column(
            "mobile_number",
            sa.String(length=20),
            nullable=False
        ),

        sa.Column(
            "otp_hash",
            sa.String(length=255),
            nullable=False
        ),

        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false")
        ),

        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0")
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP")
        ),

        sa.PrimaryKeyConstraint(
            "verification_id"
        )
    )

    op.create_index(
        "idx_mobile_verification_phone",
        "mobile_verifications",
        ["country_code", "mobile_number"],
        unique=False
    )


def downgrade() -> None:

    op.drop_index(
        "idx_mobile_verification_phone",
        table_name="mobile_verifications"
    )

    op.drop_table(
        "mobile_verifications"
    )