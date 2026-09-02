"""job_alert_updates

Revision ID: 20260701_job_alert_updates
Revises: 95e547b4302d
Create Date: 2026-07-01

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d3b8f6a1c947"
down_revision = "4a7e8d9c2f61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS job_alerts (
        alert_id TEXT PRIMARY KEY
            DEFAULT replace(gen_random_uuid()::text, '-', ''),
        candidate_id TEXT NOT NULL,
        job_alert_title VARCHAR(100),
        job_category VARCHAR(100),
        preferred_location VARCHAR(100),
        experience_level VARCHAR(50),
        employment_type VARCHAR(50),
        notification_preference VARCHAR(50),
        alert_frequency VARCHAR(30) DEFAULT 'DAILY',
        active_status BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_job_alert_candidate
            FOREIGN KEY (candidate_id)
            REFERENCES candidate_profiles(candidate_id)
    );
    """)

    # ------------------------------------------------------------------
    # Ensure columns exist for databases where the table already exists
    # ------------------------------------------------------------------

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS job_alert_title VARCHAR(100);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS job_category VARCHAR(100);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS preferred_location VARCHAR(100);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS experience_level VARCHAR(50);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS employment_type VARCHAR(50);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS notification_preference VARCHAR(50);
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS alert_frequency VARCHAR(30) DEFAULT 'DAILY';
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS active_status BOOLEAN DEFAULT TRUE;
    """)

    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    """)

    op.execute("""
    ALTER TABLE job_alerts
    DROP COLUMN IF EXISTS keyword,
    DROP COLUMN IF EXISTS location,
    DROP COLUMN IF EXISTS frequency,
    DROP COLUMN IF EXISTS is_active;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE job_alerts
    ADD COLUMN IF NOT EXISTS keyword VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location VARCHAR(255),
    ADD COLUMN IF NOT EXISTS frequency VARCHAR(50),
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
    """)

    op.execute("""
    ALTER TABLE job_alerts
    DROP COLUMN IF EXISTS job_alert_title,
    DROP COLUMN IF EXISTS job_category,
    DROP COLUMN IF EXISTS preferred_location,
    DROP COLUMN IF EXISTS experience_level,
    DROP COLUMN IF EXISTS employment_type,
    DROP COLUMN IF EXISTS notification_preference,
    DROP COLUMN IF EXISTS alert_frequency,
    DROP COLUMN IF EXISTS active_status;
    """)
