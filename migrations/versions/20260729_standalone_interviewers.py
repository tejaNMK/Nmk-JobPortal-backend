"""add standalone interviewers

Revision ID: 20260729_standalone_interviewers
Revises: 20260729_platform_activity_logs
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_standalone_interviewers"
down_revision = "20260729_platform_activity_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interviewers",
        sa.Column(
            "id",
            sa.Text(),
            server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_interviewers_email_lower",
        "interviewers",
        [sa.text("lower(email)")],
        unique=True,
    )

    op.add_column(
        "interview_interviewers",
        sa.Column("interviewer_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "interview_interviewers",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE interview_interviewers
        SET created_at = assigned_at
        WHERE assigned_at IS NOT NULL
        """
    )

    op.execute(
        """
        INSERT INTO interviewers (id, name, email, created_at, updated_at)
        SELECT
            replace(gen_random_uuid()::text, '-', ''),
            COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email),
            lower(trim(u.email)),
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM interview_interviewers ii
        JOIN users u ON u.user_id = ii.interviewer_user_id
        WHERE u.email IS NOT NULL
        ON CONFLICT (lower(email)) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE interview_interviewers ii
        SET interviewer_id = i.id
        FROM users u
        JOIN interviewers i ON i.email = lower(trim(u.email))
        WHERE u.user_id = ii.interviewer_user_id
          AND ii.interviewer_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM interview_interviewers
        WHERE interviewer_id IS NULL
        """
    )

    op.alter_column(
        "interview_interviewers",
        "interviewer_id",
        existing_type=sa.Text(),
        nullable=False,
    )

    op.drop_index(
        "idx_interview_interviewers_user_id",
        table_name="interview_interviewers",
    )
    op.drop_constraint(
        "interview_interviewers_interviewer_user_id_fkey",
        "interview_interviewers",
        type_="foreignkey",
    )
    op.drop_column("interview_interviewers", "interviewer_user_id")
    op.drop_column("interview_interviewers", "assigned_by")
    op.drop_column("interview_interviewers", "assigned_at")
    op.alter_column(
        "interview_interviewers",
        "interview_interviewer_id",
        new_column_name="id",
        existing_type=sa.Text(),
    )
    op.create_foreign_key(
        "interview_interviewers_interviewer_id_fkey",
        "interview_interviewers",
        "interviewers",
        ["interviewer_id"],
        ["id"],
    )
    op.create_index(
        "idx_interview_interviewers_interviewer_id",
        "interview_interviewers",
        ["interviewer_id"],
    )
    op.create_unique_constraint(
        "uq_interview_interviewers_interview_interviewer",
        "interview_interviewers",
        ["interview_id", "interviewer_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_interview_interviewers_interview_interviewer",
        "interview_interviewers",
        type_="unique",
    )
    op.drop_index(
        "idx_interview_interviewers_interviewer_id",
        table_name="interview_interviewers",
    )
    op.drop_constraint(
        "interview_interviewers_interviewer_id_fkey",
        "interview_interviewers",
        type_="foreignkey",
    )
    op.alter_column(
        "interview_interviewers",
        "id",
        new_column_name="interview_interviewer_id",
        existing_type=sa.Text(),
    )
    op.add_column(
        "interview_interviewers",
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "interview_interviewers",
        sa.Column("assigned_by", sa.Text(), nullable=True),
    )
    op.add_column(
        "interview_interviewers",
        sa.Column("interviewer_user_id", sa.UUID(), nullable=True),
    )
    op.drop_column("interview_interviewers", "created_at")
    op.drop_column("interview_interviewers", "interviewer_id")
    op.create_foreign_key(
        "interview_interviewers_interviewer_user_id_fkey",
        "interview_interviewers",
        "users",
        ["interviewer_user_id"],
        ["user_id"],
    )
    op.create_index(
        "idx_interview_interviewers_user_id",
        "interview_interviewers",
        ["interviewer_user_id"],
    )
    op.drop_index("uq_interviewers_email_lower", table_name="interviewers")
    op.drop_table("interviewers")
