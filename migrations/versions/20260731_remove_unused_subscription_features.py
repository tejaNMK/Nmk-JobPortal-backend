"""remove unused subscription feature flags

Revision ID: 20260731_remove_unused_sub_features
Revises: 20260731_company_timestamps
Create Date: 2026-07-31 00:00:00.000000

"""

from alembic import op


revision = "20260731_remove_unused_sub_features"
down_revision = "20260731_company_timestamps"
branch_labels = None
depends_on = None


REMOVED_FEATURE_KEYS = (
    "advancedCandidateFilters",
    "advanced_candidate_filters",
    "aiCareerSuggestions",
    "aiResumeReview",
    "aiSkillMatching",
    "ai_career_suggestions",
    "ai_resume_review",
    "ai_skill_matching",
    "applicantTracking",
    "applicant_tracking",
    "bulkCandidateActions",
    "bulk_candidate_actions",
    "candidateAnalytics",
    "candidate_analytics",
    "companyBanner",
    "companyLogo",
    "company_banner",
    "company_logo",
    "coverLetterBuilder",
    "cover_letter_builder",
    "dashboardReports",
    "dashboard_reports",
    "dedicatedAccountManager",
    "dedicated_account_manager",
    "emailNotifications",
    "email_notifications",
    "featuredCandidateBadge",
    "featuredCompany",
    "featuredJobPosts",
    "featured_candidate_badge",
    "featured_company",
    "featured_job_posts",
    "instantEmailNotifications",
    "instant_email_notifications",
    "interviewScheduling",
    "interview_scheduling",
    "jobAnalytics",
    "job_analytics",
    "mockInterviewAccess",
    "mock_interview_access",
    "multipleRecruiterAccess",
    "multiple_recruiter_access",
    "priorityCustomerSupport",
    "priorityProfileInSearchResults",
    "prioritySupport",
    "priority_customer_support",
    "priority_profile_in_search_results",
    "priority_support",
    "profileHighlight",
    "profile_highlight",
    "resumeDownloadsLimit",
    "resume_downloads_limit",
    "skillAssessmentAccess",
    "skill_assessment_access",
    "smsNotifications",
    "sms_notifications",
    "talentPoolAccess",
    "talent_pool_access",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS alembic_version
        ALTER COLUMN version_num TYPE varchar(255)
        """
    )

    keys_sql = ", ".join(f"'{key}'" for key in REMOVED_FEATURE_KEYS)
    op.execute(
        f"""
        UPDATE subscriptions
        SET feature_flags = (COALESCE(feature_flags::jsonb, '{{}}'::jsonb) - ARRAY[{keys_sql}])::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE feature_flags IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
