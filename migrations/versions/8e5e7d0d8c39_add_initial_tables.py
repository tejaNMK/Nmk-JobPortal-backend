"""Add initial user-service tables

Revision ID: 8e5e7d0d8c39
Revises:
Create Date: 2023-03-17 02:43:41.896936

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "8e5e7d0d8c39"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("mobile_number", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("profile_image_url", sa.Text(), nullable=True),
        sa.Column(
            "user_status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False
        ),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False
        ),
        sa.Column(
            "mobile_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False
        ),
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False
        ),
        sa.Column(
            "account_locked",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "deleted_flag",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "email IS NOT NULL OR mobile_number IS NOT NULL",
            name="chk_contact_method"
        ),
        sa.CheckConstraint(
            "user_status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'LOCKED')",
            name="chk_users_status"
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("mobile_number", name="uq_users_mobile"),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_mobile", "users", ["mobile_number"])
    op.create_index("idx_users_status", "users", ["user_status"])
    op.create_index("idx_users_deleted_flag", "users", ["deleted_flag"])
    op.create_index("idx_users_last_login", "users", ["last_login_at"])

    op.create_table(
        "roles",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column("role_name", sa.String(length=100), nullable=False),
        sa.Column("role_code", sa.String(length=100), nullable=False),
        sa.Column("role_description", sa.Text(), nullable=True),
        sa.Column(
            "active_flag",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("role_code", name="uq_roles_code"),
    )

    roles_table = sa.table(
        "roles",
        sa.column("role_name", sa.String),
        sa.column("role_code", sa.String),
    )
    op.bulk_insert(
        roles_table,
        [
            {"role_name": "Admin", "role_code": "ROLE_ADMIN"},
            {"role_name": "Recruiter", "role_code": "ROLE_RECRUITER"},
            {"role_name": "Candidate", "role_code": "ROLE_CANDIDATE"},
        ],
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_role_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "active_flag",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.role_id"],
            name="fk_user_roles_role"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_user_roles_user"
        ),
        sa.PrimaryKeyConstraint("user_role_id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    op.create_table(
        "user_sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jwt_id", sa.String(length=255), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=500), nullable=True),
        sa.Column("login_method", sa.String(length=20), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_type", sa.String(length=100), nullable=True),
        sa.Column(
            "login_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.Column("logout_at", sa.DateTime(), nullable=True),
        sa.Column(
            "session_status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.CheckConstraint(
            "login_method IN ('EMAIL', 'MOBILE')",
            name="chk_login_method"
        ),
        sa.CheckConstraint(
            "session_status IN ('ACTIVE', 'LOGGED_OUT', 'EXPIRED')",
            name="chk_session_status"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_user_sessions_user"
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("idx_user_sessions_user", "user_sessions", ["user_id"])
    op.create_index(
        "idx_user_sessions_status",
        "user_sessions",
        ["session_status"]
    )
    op.create_index(
        "idx_user_sessions_login_at",
        "user_sessions",
        ["login_at"]
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "token_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reset_token_hash", sa.String(length=500), nullable=True),
        sa.Column("otp_code_hash", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "used_flag",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_password_reset_user"
        ),
        sa.PrimaryKeyConstraint("token_id"),
    )

    op.create_table(
        "password_history",
        sa.Column(
            "history_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_password_history_user"
        ),
        sa.PrimaryKeyConstraint("history_id"),
    )

    _create_application_baseline_tables()


def _create_application_baseline_tables() -> None:
    """Create legacy application tables that originally came from create_all().

    This root revision is the schema baseline for empty databases. Tables
    introduced by later non-idempotent revisions intentionally remain outside
    this baseline.
    """

    op.execute("""
CREATE TABLE job_posting_audit (
    audit_id SERIAL NOT NULL,
    employer_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    actor_user_id TEXT,
    actor_email TEXT,
    PRIMARY KEY (audit_id)
);
""")
    op.execute("CREATE INDEX idx_job_posting_audit_event_type ON job_posting_audit (event_type)")
    op.execute("CREATE INDEX idx_job_posting_audit_employer_id ON job_posting_audit (employer_id)")
    op.execute("CREATE INDEX idx_job_posting_audit_job_id ON job_posting_audit (job_id)")
    op.execute("CREATE INDEX ix_job_posting_audit_employer_id ON job_posting_audit (employer_id)")
    op.execute("CREATE INDEX ix_job_posting_audit_job_id ON job_posting_audit (job_id)")

    op.execute("""
CREATE TABLE message_threads (
    thread_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    subject VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (thread_id)
);
""")

    op.execute("""
CREATE TABLE person (
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    PRIMARY KEY (id)
);
""")

    op.execute("""
CREATE TABLE search_keywords (
    keyword_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    suggestion_text TEXT,
    hit_count BIGINT DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (keyword_id)
);
""")

    op.execute("""
CREATE TABLE candidate_profiles (
    candidate_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    user_id UUID NOT NULL,
    headline VARCHAR(255),
    summary TEXT,
    total_experience NUMERIC(5, 2),
    current_location VARCHAR(255),
    preferred_location VARCHAR(255),
    website_url TEXT,
    portfolio_url TEXT,
    skills_summary TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    dribbble_url TEXT,
    twitter_url TEXT,
    profile_completion_pct INTEGER DEFAULT 0,
    application_count INTEGER DEFAULT 0,
    active_resume_id TEXT,
    profile_visibility VARCHAR(20) DEFAULT 'PRIVATE',
    searchable_flag BOOLEAN DEFAULT true,
    open_to_work BOOLEAN DEFAULT false,
    experience_level VARCHAR(100),
    current_company VARCHAR(255),
    notice_period VARCHAR(100),
    desired_employment VARCHAR(100),
    salary_expectation VARCHAR(100),
    work_preference VARCHAR(100),
    target_roles TEXT,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    updated_by TEXT,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    deleted_by TEXT,
    PRIMARY KEY (candidate_id),
    UNIQUE (user_id),
    FOREIGN KEY(user_id) REFERENCES users (user_id)
);
""")
    op.execute("CREATE INDEX idx_candidate_profiles_user ON candidate_profiles (user_id)")

    op.execute("""
CREATE TABLE employer_profiles (
    id TEXT NOT NULL,
    user_id UUID NOT NULL,
    company_name TEXT NOT NULL,
    company_email TEXT,
    company_mobile TEXT,
    company_website TEXT,
    company_logo_url TEXT,
    industry TEXT,
    company_size TEXT,
    company_description TEXT,
    company_location TEXT,
    established_year INTEGER,
    linkedin_url TEXT,
    gst_number TEXT,
    registration_number TEXT,
    is_verified INTEGER DEFAULT 0 NOT NULL,
    verification_status TEXT DEFAULT 'PENDING' NOT NULL,
    status TEXT DEFAULT 'ACTIVE' NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by TEXT,
    updated_by TEXT,
    is_deleted INTEGER DEFAULT 0 NOT NULL,
    deleted_at TEXT,
    version INTEGER DEFAULT 0 NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (user_id),
    FOREIGN KEY(user_id) REFERENCES users (user_id)
);
""")

    op.execute("""
CREATE TABLE messages (
    message_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    thread_id TEXT NOT NULL,
    sender_id UUID,
    receiver_id UUID,
    message_body TEXT,
    sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    read_flag BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    PRIMARY KEY (message_id),
    FOREIGN KEY(thread_id) REFERENCES message_threads (thread_id),
    FOREIGN KEY(sender_id) REFERENCES users (user_id),
    FOREIGN KEY(receiver_id) REFERENCES users (user_id)
);
""")

    op.execute("""
CREATE TABLE candidate_resume_details (
    resume_detail_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    education_json JSONB,
    experience_json JSONB,
    skills_json JSONB,
    certifications_json JSONB,
    projects_json JSONB,
    languages_json JSONB,
    generated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT false,
    PRIMARY KEY (resume_detail_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id)
);
""")

    op.execute("""
CREATE TABLE candidate_resumes (
    resume_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    version_no INTEGER DEFAULT 1,
    file_name VARCHAR(255),
    file_path TEXT,
    blob_ref TEXT,
    is_active BOOLEAN DEFAULT true,
    uploaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    updated_by TEXT,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (resume_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id)
);
""")
    op.execute("CREATE INDEX idx_candidate_resumes_candidate ON candidate_resumes (candidate_id)")

    op.execute("""
CREATE TABLE candidate_saved_searches (
    saved_search_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    search_name VARCHAR(255),
    keywords TEXT,
    skills TEXT,
    location VARCHAR(255),
    work_mode VARCHAR(50),
    salary_min NUMERIC(12, 2),
    salary_max NUMERIC(12, 2),
    experience_min NUMERIC(5, 2),
    experience_max NUMERIC(5, 2),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (saved_search_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id)
);
""")

    op.execute("""
CREATE TABLE company_profiles (
    company_id TEXT NOT NULL,
    employer_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    website TEXT,
    logo_path TEXT,
    description TEXT,
    industry TEXT,
    size TEXT,
    location TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (company_id),
    FOREIGN KEY(employer_id) REFERENCES employer_profiles (id)
);
""")
    op.execute("CREATE INDEX idx_company_name ON company_profiles (company_name)")

    op.execute("""
CREATE TABLE job_alerts (
    alert_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    job_alert_title VARCHAR(100),
    job_category VARCHAR(100),
    preferred_location VARCHAR(100),
    experience_level VARCHAR(50),
    employment_type VARCHAR(50),
    notification_preference VARCHAR(50),
    alert_frequency VARCHAR(30),
    active_status BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (alert_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id)
);
""")

    op.execute("""
CREATE TABLE jobs (
    job_id TEXT NOT NULL,
    employer_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    employment_type TEXT NOT NULL,
    experience_min INTEGER,
    experience_max INTEGER,
    location TEXT,
    work_mode TEXT,
    salary_min FLOAT,
    salary_max FLOAT,
    salary_currency VARCHAR(10) DEFAULT 'USD' NOT NULL,
    salary_period VARCHAR(20) DEFAULT 'Monthly' NOT NULL,
    no_of_openings INTEGER DEFAULT 1 NOT NULL,
    application_deadline TIMESTAMP WITHOUT TIME ZONE,
    status TEXT DEFAULT 'DRAFT' NOT NULL,
    copied_from_job_id TEXT,
    closed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by TEXT,
    updated_by TEXT,
    is_deleted BOOLEAN DEFAULT false NOT NULL,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    version INTEGER DEFAULT 0 NOT NULL,
    company_name TEXT,
    contact_email TEXT,
    idempotency_key TEXT,
    PRIMARY KEY (job_id),
    CONSTRAINT chk_experience_min_positive CHECK (experience_min >= 0),
    CONSTRAINT chk_experience_range CHECK (experience_max >= experience_min),
    CONSTRAINT chk_salary_min_positive CHECK (salary_min >= 0),
    CONSTRAINT chk_salary_range CHECK (salary_max >= salary_min),
    CONSTRAINT chk_openings_positive CHECK (no_of_openings > 0),
    FOREIGN KEY(employer_id) REFERENCES employer_profiles (id),
    FOREIGN KEY(copied_from_job_id) REFERENCES jobs (job_id)
);
""")
    op.execute("CREATE INDEX idx_jobs_created_at ON jobs (created_at)")
    op.execute("CREATE INDEX idx_jobs_employer ON jobs (employer_id)")
    op.execute("CREATE INDEX idx_jobs_employer_status ON jobs (employer_id, status)")
    op.execute("CREATE UNIQUE INDEX idx_jobs_employer_idempotency ON jobs (employer_id, idempotency_key) WHERE idempotency_key IS NOT NULL")
    op.execute("CREATE INDEX idx_jobs_location ON jobs (location)")
    op.execute("CREATE INDEX idx_jobs_status ON jobs (status)")
    op.execute("CREATE INDEX ix_jobs_employer_id ON jobs (employer_id)")
    op.execute("CREATE INDEX ix_jobs_idempotency_key ON jobs (idempotency_key)")

    op.execute("""
CREATE TABLE profile_view_events (
    view_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    viewer_user_id UUID,
    viewer_ip TEXT,
    viewed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (view_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id),
    FOREIGN KEY(viewer_user_id) REFERENCES users (user_id)
);
""")
    op.execute("CREATE INDEX idx_pve_candidate_id ON profile_view_events (candidate_id)")
    op.execute("CREATE INDEX idx_pve_viewed_at ON profile_view_events (viewed_at)")

    op.execute("""
CREATE TABLE candidate_company_followings (
    following_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    followed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT false NOT NULL,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (following_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id),
    FOREIGN KEY(company_id) REFERENCES company_profiles (company_id)
);
""")
    op.execute("CREATE INDEX idx_ccf_candidate_id ON candidate_company_followings (candidate_id)")
    op.execute("CREATE INDEX idx_ccf_company_id ON candidate_company_followings (company_id)")

    op.execute("""
CREATE TABLE candidate_recommendations (
    recommendation_id TEXT NOT NULL,
    employer_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    match_score FLOAT,
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recommendation_id),
    FOREIGN KEY(employer_id) REFERENCES employer_profiles (id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")

    op.execute("""
CREATE TABLE candidate_saved_jobs (
    saved_job_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    saved_flag BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (saved_job_id),
    UNIQUE (candidate_id, job_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")
    op.execute("CREATE INDEX idx_candidate_saved_jobs_candidate ON candidate_saved_jobs (candidate_id)")

    op.execute("""
CREATE TABLE job_applications (
    application_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    resume_id TEXT,
    application_status VARCHAR(50) DEFAULT 'APPLIED',
    cover_letter_text TEXT,
    recruiter_notes_ref TEXT,
    recruiter_notes TEXT,
    source VARCHAR(100),
    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    referral_contact VARCHAR(255),
    next_step_text VARCHAR(500),
    next_step_due DATE,
    interview_loop_date DATE,
    candidate_rating INTEGER,
    shortlisted_at TIMESTAMP WITHOUT TIME ZONE,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (application_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id),
    FOREIGN KEY(resume_id) REFERENCES candidate_resumes (resume_id)
);
""")
    op.execute("CREATE INDEX idx_job_applications_candidate ON job_applications (candidate_id)")
    op.execute("CREATE INDEX idx_job_applications_job ON job_applications (job_id)")

    op.execute("""
CREATE TABLE job_metrics (
    metric_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    view_count INTEGER DEFAULT 0,
    application_count INTEGER DEFAULT 0,
    shortlist_count INTEGER DEFAULT 0,
    last_viewed_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (metric_id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")

    op.execute("""
CREATE TABLE job_recommendations (
    recommendation_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    match_score NUMERIC(5, 2),
    generated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (recommendation_id),
    FOREIGN KEY(candidate_id) REFERENCES candidate_profiles (candidate_id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")

    op.execute("""
CREATE TABLE job_skills (
    job_id TEXT NOT NULL,
    skill TEXT NOT NULL,
    PRIMARY KEY (job_id, skill),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")

    op.execute("""
CREATE TABLE shortlisted_candidates (
    shortlist_id TEXT NOT NULL,
    employer_id TEXT NOT NULL,
    recruiter_id TEXT,
    candidate_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    shortlisted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'ACTIVE',
    remarks TEXT,
    PRIMARY KEY (shortlist_id),
    FOREIGN KEY(employer_id) REFERENCES employer_profiles (id),
    FOREIGN KEY(job_id) REFERENCES jobs (job_id)
);
""")
    op.execute("CREATE INDEX idx_shortlisted_candidate ON shortlisted_candidates (candidate_id)")

    op.execute("""
CREATE TABLE application_notes (
    note_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    application_id TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_by TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT false,
    deleted_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (note_id),
    FOREIGN KEY(application_id) REFERENCES job_applications (application_id)
);
""")

    op.execute("""
CREATE TABLE application_status_history (
    history_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    application_id TEXT NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    changed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    changed_by UUID,
    PRIMARY KEY (history_id),
    FOREIGN KEY(application_id) REFERENCES job_applications (application_id),
    FOREIGN KEY(changed_by) REFERENCES users (user_id)
);
""")

    op.execute("""
CREATE TABLE interviews (
    interview_id TEXT DEFAULT replace(gen_random_uuid()::text, '-', '') NOT NULL,
    application_id TEXT NOT NULL,
    scheduled_at TIMESTAMP WITHOUT TIME ZONE,
    mode TEXT,
    location_or_link TEXT,
    interviewer_name TEXT,
    status TEXT DEFAULT 'SCHEDULED',
    notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (interview_id),
    FOREIGN KEY(application_id) REFERENCES job_applications (application_id)
);
""")


def downgrade() -> None:
    op.drop_table("interviews")
    op.drop_table("application_status_history")
    op.drop_table("application_notes")
    op.drop_index("idx_shortlisted_candidate", table_name="shortlisted_candidates")
    op.drop_table("shortlisted_candidates")
    op.drop_table("job_skills")
    op.drop_table("job_recommendations")
    op.drop_table("job_metrics")
    op.drop_index("idx_job_applications_job", table_name="job_applications")
    op.drop_index("idx_job_applications_candidate", table_name="job_applications")
    op.drop_table("job_applications")
    op.drop_index("idx_candidate_saved_jobs_candidate", table_name="candidate_saved_jobs")
    op.drop_table("candidate_saved_jobs")
    op.drop_table("candidate_recommendations")
    op.drop_index("idx_ccf_company_id", table_name="candidate_company_followings")
    op.drop_index("idx_ccf_candidate_id", table_name="candidate_company_followings")
    op.drop_table("candidate_company_followings")
    op.drop_index("idx_pve_viewed_at", table_name="profile_view_events")
    op.drop_index("idx_pve_candidate_id", table_name="profile_view_events")
    op.drop_table("profile_view_events")
    op.drop_index("ix_jobs_idempotency_key", table_name="jobs")
    op.drop_index("ix_jobs_employer_id", table_name="jobs")
    op.drop_index("idx_jobs_status", table_name="jobs")
    op.drop_index("idx_jobs_location", table_name="jobs")
    op.drop_index("idx_jobs_employer_idempotency", table_name="jobs")
    op.drop_index("idx_jobs_employer_status", table_name="jobs")
    op.drop_index("idx_jobs_employer", table_name="jobs")
    op.drop_index("idx_jobs_created_at", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("job_alerts")
    op.drop_index("idx_company_name", table_name="company_profiles")
    op.drop_table("company_profiles")
    op.drop_table("candidate_saved_searches")
    op.drop_index("idx_candidate_resumes_candidate", table_name="candidate_resumes")
    op.drop_table("candidate_resumes")
    op.drop_table("candidate_resume_details")
    op.drop_table("messages")
    op.drop_table("employer_profiles")
    op.drop_index("idx_candidate_profiles_user", table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
    op.drop_table("search_keywords")
    op.drop_table("person")
    op.drop_table("message_threads")
    op.drop_index("ix_job_posting_audit_job_id", table_name="job_posting_audit")
    op.drop_index("ix_job_posting_audit_employer_id", table_name="job_posting_audit")
    op.drop_index("idx_job_posting_audit_job_id", table_name="job_posting_audit")
    op.drop_index("idx_job_posting_audit_employer_id", table_name="job_posting_audit")
    op.drop_index("idx_job_posting_audit_event_type", table_name="job_posting_audit")
    op.drop_table("job_posting_audit")
    op.drop_table("password_history")
    op.drop_table("password_reset_tokens")
    op.drop_index("idx_user_sessions_login_at", table_name="user_sessions")
    op.drop_index("idx_user_sessions_status", table_name="user_sessions")
    op.drop_index("idx_user_sessions_user", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_index("idx_users_last_login", table_name="users")
    op.drop_index("idx_users_deleted_flag", table_name="users")
    op.drop_index("idx_users_status", table_name="users")
    op.drop_index("idx_users_mobile", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
