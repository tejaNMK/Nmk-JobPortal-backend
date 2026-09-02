"""complete interview scheduling schema

Revision ID: a9c3e2d7f604
Revises: 7a2c5e9f1b34
Create Date: 2026-07-06 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a9c3e2d7f604"
down_revision = "7a2c5e9f1b34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("interview_round", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("interview_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("interview_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("meeting_link", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("interview_location", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )

    op.execute("""
        UPDATE interviews
        SET
            interview_date = scheduled_at::date,
            interview_time = scheduled_at::time
        WHERE scheduled_at IS NOT NULL
    """)
    op.execute("""
        UPDATE interviews
        SET meeting_link = location_or_link
        WHERE mode = 'ONLINE'
    """)
    op.execute("""
        UPDATE interviews
        SET interview_location = location_or_link
        WHERE mode <> 'ONLINE' OR mode IS NULL
    """)

    op.alter_column(
        "interviews",
        "notes",
        new_column_name="remarks",
        existing_type=sa.Text(),
    )
    op.drop_column("interviews", "scheduled_at")
    op.drop_column("interviews", "location_or_link")

    op.create_table(
        "interview_history",
        sa.Column(
            "history_id",
            sa.Text(),
            server_default=sa.text(
                "replace(gen_random_uuid()::text, '-', '')"
            ),
            nullable=False,
        ),
        sa.Column("interview_id", sa.Text(), nullable=False),
        sa.Column("application_id", sa.Text(), nullable=False),
        sa.Column("employer_id", sa.Text(), nullable=False),
        sa.Column("performed_by", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("previous_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["job_applications.application_id"],
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.interview_id"],
        ),
        sa.PrimaryKeyConstraint("history_id"),
    )


def downgrade() -> None:
    op.drop_table("interview_history")

    op.add_column(
        "interviews",
        sa.Column("location_or_link", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
    )

    op.execute("""
        UPDATE interviews
        SET scheduled_at = interview_date + interview_time
        WHERE interview_date IS NOT NULL
          AND interview_time IS NOT NULL
    """)
    op.execute("""
        UPDATE interviews
        SET location_or_link = COALESCE(meeting_link, interview_location)
    """)

    op.alter_column(
        "interviews",
        "remarks",
        new_column_name="notes",
        existing_type=sa.Text(),
    )
    op.drop_column("interviews", "updated_at")
    op.drop_column("interviews", "interview_location")
    op.drop_column("interviews", "meeting_link")
    op.drop_column("interviews", "interview_time")
    op.drop_column("interviews", "interview_date")
    op.drop_column("interviews", "interview_round")
