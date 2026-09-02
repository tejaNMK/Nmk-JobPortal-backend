from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator


EMPLOYER_FEATURE_FLAGS_EXAMPLE: dict[str, Any] = {
    "ai_job_description_generator": True,
    "ai_job_description_generations_per_month": None,
    "ai_message_drafting": True,
    "ai_message_drafts_per_month": None,
    "ai_candidate_insights": True,
    "ai_candidate_insights_per_month": None,
    "candidateSearch": True,
    "recruiterAccounts": None,
}

CANDIDATE_FEATURE_FLAGS_EXAMPLE: dict[str, Any] = {
    "job_alerts": True,
    "resume_builder": True,
    "saved_jobs_limit": None,
    "resume_visibility": True,
    "recruiters_can_contact_candidate": True,
}

EMPLOYER_SUBSCRIPTION_EXAMPLE: dict[str, Any] = {
    "subscription_name": "Default Employer Plan",
    "subscription_type": "EMPLOYER",
    "description": "System default employer subscription plan.",
    "price": "0.00",
    "currency": "INR",
    "duration_days": 3650,
    "billing_cycle": "Monthly",
    "display_order": 999,
    "max_published_jobs": None,
    "max_job_alerts": None,
    "max_resume_uploads": None,
    "saved_jobs_limit": None,
    "candidate_invitations": True,
    "candidate_invitations_per_week": 25,
    "ai_job_description_generator": True,
    "ai_job_description_generations_per_month": None,
    "ai_message_drafting": True,
    "ai_message_drafts_per_month": None,
    "ai_candidate_insights": True,
    "ai_candidate_insights_per_month": None,
    "feature_flags": EMPLOYER_FEATURE_FLAGS_EXAMPLE,
    "features": EMPLOYER_FEATURE_FLAGS_EXAMPLE,
    "is_featured": False,
    "is_popular": False,
    "is_active": True,
    "is_default": True,
}

CANDIDATE_SUBSCRIPTION_EXAMPLE: dict[str, Any] = {
    "subscription_name": "Default Candidate Plan",
    "subscription_type": "CANDIDATE",
    "description": "System default candidate subscription plan.",
    "price": "0.00",
    "currency": "INR",
    "duration_days": 3650,
    "billing_cycle": "Monthly",
    "display_order": 999,
    "max_published_jobs": None,
    "max_job_alerts": None,
    "max_resume_uploads": None,
    "saved_jobs_limit": None,
    "candidate_invitations": None,
    "candidate_invitations_per_week": None,
    "feature_flags": CANDIDATE_FEATURE_FLAGS_EXAMPLE,
    "features": CANDIDATE_FEATURE_FLAGS_EXAMPLE,
    "is_featured": False,
    "is_popular": True,
    "is_active": True,
    "is_default": True,
}

EMPLOYER_SUBSCRIPTION_RESPONSE_EXAMPLE: dict[str, Any] = {
    **EMPLOYER_SUBSCRIPTION_EXAMPLE,
    "subscription_id": "fd0220a4-5784-427e-8796-07250e2d4f5c",
    "created_at": "2026-07-29T05:20:56.106602",
    "updated_at": "2026-07-29T05:38:24.663500",
    "created_by": None,
    "updated_by": None,
    "status": "Active",
    "popular_plan": False,
}

CANDIDATE_SUBSCRIPTION_RESPONSE_EXAMPLE: dict[str, Any] = {
    **CANDIDATE_SUBSCRIPTION_EXAMPLE,
    "subscription_id": "f4b1019a-72ea-4189-9a14-81230cd8b0f3",
    "created_at": "2026-07-29T05:20:56.098097",
    "updated_at": "2026-07-29T05:38:24.658796",
    "created_by": None,
    "updated_by": None,
    "status": "Active",
    "popular_plan": True,
}

SUBSCRIPTION_SCHEMA_EXAMPLES = [
    EMPLOYER_SUBSCRIPTION_EXAMPLE,
    CANDIDATE_SUBSCRIPTION_EXAMPLE,
]

SUBSCRIPTION_RESPONSE_SCHEMA_EXAMPLES = [
    EMPLOYER_SUBSCRIPTION_RESPONSE_EXAMPLE,
    CANDIDATE_SUBSCRIPTION_RESPONSE_EXAMPLE,
]


class SubscriptionBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": SUBSCRIPTION_SCHEMA_EXAMPLES},
    )

    subscription_name: str = Field(min_length=1, max_length=150)
    subscription_type: str = Field(min_length=1, max_length=30)
    description: Optional[str] = None

    price: Decimal = Field(ge=Decimal("0"))

    currency: str = Field(default="INR", min_length=3, max_length=10)

    duration_days: int = Field(gt=0)
    billing_cycle: str = Field(default="Monthly", min_length=1, max_length=30)
    display_order: int = Field(default=1, ge=0)

    max_published_jobs: Optional[int] = Field(default=None, ge=0)
    max_job_alerts: Optional[int] = Field(default=None, ge=0)
    max_resume_uploads: Optional[int] = Field(default=None, ge=0)
    saved_jobs_limit: Optional[int] = Field(default=None, ge=0)
    candidate_invitations: Optional[bool] = None
    candidate_invitations_per_week: Optional[int] = Field(default=None, ge=0)
    ai_job_description_generator: Optional[bool] = None
    ai_job_description_generations_per_month: Optional[int] = Field(default=None, ge=0)
    ai_candidate_insights: Optional[bool] = None
    ai_candidate_insights_per_month: Optional[int] = Field(default=None, ge=0)
    ai_message_drafting: Optional[bool] = None
    ai_message_drafts_per_month: Optional[int] = Field(default=None, ge=0)
    feature_flags: dict[str, Any] = Field(
        default_factory=dict,
        examples=[EMPLOYER_FEATURE_FLAGS_EXAMPLE, CANDIDATE_FEATURE_FLAGS_EXAMPLE],
    )
    features: Optional[dict[str, Any]] = Field(
        default=None,
        examples=[EMPLOYER_FEATURE_FLAGS_EXAMPLE, CANDIDATE_FEATURE_FLAGS_EXAMPLE],
    )

    is_featured: bool = False
    is_popular: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_popular", "popular_plan"),
    )
    is_active: bool = True
    is_default: bool = False

    @field_validator("subscription_type")
    @classmethod
    def normalize_subscription_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"CANDIDATE", "EMPLOYER", "ADMIN"}:
            raise ValueError("subscription_type must be CANDIDATE, EMPLOYER, or ADMIN")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class SubscriptionCreate(SubscriptionBase):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"examples": SUBSCRIPTION_SCHEMA_EXAMPLES},
    )

    status: Optional[bool | str] = None


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={
            "examples": SUBSCRIPTION_SCHEMA_EXAMPLES,
        },
    )

    subscription_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    subscription_type: Optional[str] = Field(default=None, min_length=1, max_length=30)
    description: Optional[str] = None

    price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))

    currency: Optional[str] = Field(default=None, min_length=3, max_length=10)

    duration_days: Optional[int] = Field(default=None, gt=0)
    billing_cycle: Optional[str] = Field(default=None, min_length=1, max_length=30)
    display_order: Optional[int] = Field(default=None, ge=0)

    max_published_jobs: Optional[int] = Field(default=None, ge=0)
    max_job_alerts: Optional[int] = Field(default=None, ge=0)
    max_resume_uploads: Optional[int] = Field(default=None, ge=0)
    saved_jobs_limit: Optional[int] = Field(default=None, ge=0)
    candidate_invitations: Optional[bool] = None
    candidate_invitations_per_week: Optional[int] = Field(default=None, ge=0)
    ai_job_description_generator: Optional[bool] = None
    ai_job_description_generations_per_month: Optional[int] = Field(default=None, ge=0)
    ai_candidate_insights: Optional[bool] = None
    ai_candidate_insights_per_month: Optional[int] = Field(default=None, ge=0)
    ai_message_drafting: Optional[bool] = None
    ai_message_drafts_per_month: Optional[int] = Field(default=None, ge=0)
    feature_flags: Optional[dict[str, Any]] = Field(
        default=None,
        examples=[EMPLOYER_FEATURE_FLAGS_EXAMPLE, CANDIDATE_FEATURE_FLAGS_EXAMPLE],
    )
    features: Optional[dict[str, Any]] = Field(
        default=None,
        examples=[EMPLOYER_FEATURE_FLAGS_EXAMPLE, CANDIDATE_FEATURE_FLAGS_EXAMPLE],
    )

    is_featured: Optional[bool] = None
    is_popular: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("is_popular", "popular_plan"),
    )
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    status: Optional[bool | str] = None

    @field_validator("subscription_type")
    @classmethod
    def normalize_subscription_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {"CANDIDATE", "EMPLOYER", "ADMIN"}:
            raise ValueError("subscription_type must be CANDIDATE, EMPLOYER, or ADMIN")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class SubscriptionResponse(SubscriptionBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={"examples": SUBSCRIPTION_RESPONSE_SCHEMA_EXAMPLES},
    )

    subscription_id: UUID

    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    @computed_field
    @property
    def status(self) -> str:
        return "Active" if self.is_active else "Inactive"

    @computed_field
    @property
    def popular_plan(self) -> bool:
        return self.is_popular


class SubscriptionCatalogueResponse(SubscriptionBase):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    subscription_id: UUID
    is_current: bool = False
