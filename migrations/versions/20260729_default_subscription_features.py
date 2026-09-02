"""default subscription features

Revision ID: 20260729_default_sub_features
Revises: 20260728_role_default_settings
Create Date: 2026-07-29 00:00:00.000000
"""

import json

from alembic import op


revision = "20260729_default_sub_features"
down_revision = "20260728_role_default_settings"
branch_labels = None
depends_on = None


CANDIDATE_DEFAULT_FEATURES = {
    "job_alerts": True,
    "recruiters_can_contact_candidate": True,
    "resume_builder": True,
    "resume_upload": True,
    "resume_visibility": True,
    "unlimited_job_applications": True,
}

EMPLOYER_DEFAULT_FEATURES = {
    "candidateInvitations": True,
    "candidateSearch": True,
    "companyProfile": True,
    "unlimitedJobPosts": True,
}


def _merge_default_features(subscription_type: str, features: dict) -> None:
    feature_json = json.dumps(features, sort_keys=True)
    op.execute(
        f"""
        UPDATE subscriptions
        SET feature_flags = (
                COALESCE(feature_flags::jsonb, '{{}}'::jsonb)
                || '{feature_json}'::jsonb
            )::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE upper(subscription_type) = '{subscription_type}'
          AND subscription_name = 'Default {subscription_type.title()} Plan'
        """
    )


def upgrade() -> None:
    _merge_default_features("CANDIDATE", CANDIDATE_DEFAULT_FEATURES)
    _merge_default_features("EMPLOYER", EMPLOYER_DEFAULT_FEATURES)


def downgrade() -> None:
    pass
