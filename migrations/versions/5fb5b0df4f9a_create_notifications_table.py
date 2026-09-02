"""create_notifications_table

Revision ID: 5fb5b0df4f9a
Revises: 3d7c1a9f5e62
Create Date: 2026-07-21 10:08:52.316483

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5fb5b0df4f9a"
down_revision = "3d7c1a9f5e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",

        sa.Column(
            "notification_id",
            sa.Text(),
            nullable=False,
            server_default=sa.text(
                "replace(gen_random_uuid()::text, '-', '')"
            ),
        ),

        sa.Column(
            "recipient_id",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "notification_type",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "reference_type",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "reference_id",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        sa.Column(
            "read_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),

        sa.PrimaryKeyConstraint("notification_id"),
    )

    op.create_index(
        "idx_notifications_recipient",
        "notifications",
        ["recipient_id"],
        unique=False,
    )

    op.create_index(
        "idx_notifications_created_at",
        "notifications",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "idx_notifications_is_read",
        "notifications",
        ["is_read"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_notifications_is_read",
        table_name="notifications",
    )

    op.drop_index(
        "idx_notifications_created_at",
        table_name="notifications",
    )

    op.drop_index(
        "idx_notifications_recipient",
        table_name="notifications",
    )

    op.drop_table("notifications")