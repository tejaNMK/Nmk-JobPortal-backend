"""create_contact_us_inquiries

Revision ID: 95e547b4302d
Revises: 89406069b60c
Create Date: 2026-06-29 21:54:39.522226

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "95e547b4302d"
down_revision = "89406069b60c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_us_inquiries (

            inquiry_id TEXT PRIMARY KEY
                DEFAULT replace(gen_random_uuid()::text, '-', ''),

            full_name TEXT NOT NULL,

            email TEXT NOT NULL,

            phone_number TEXT,

            inquiry_type TEXT NOT NULL,

            custom_subject TEXT,

            message TEXT NOT NULL,

            email_status TEXT NOT NULL
                DEFAULT 'PENDING'
                CHECK (email_status IN ('PENDING', 'SENT', 'FAILED')),

            retry_count INTEGER NOT NULL
                DEFAULT 0,

            created_at TIMESTAMP WITH TIME ZONE NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            created_by TEXT,

            updated_by TEXT,

            is_deleted INTEGER NOT NULL
                DEFAULT 0,

            deleted_at TIMESTAMP WITH TIME ZONE
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_us_email
        ON contact_us_inquiries(email)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_us_email_status
        ON contact_us_inquiries(email_status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_us_created_at
        ON contact_us_inquiries(created_at)
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_contact_us_created_at
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_contact_us_email_status
    """)

    op.execute("""
        DROP INDEX IF EXISTS idx_contact_us_email
    """)

    op.execute("""
        DROP TABLE IF EXISTS contact_us_inquiries
    """)