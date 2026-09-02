from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FollowingSortBy = Literal[
    "FOLLOWED_DATE_DESC",
    "FOLLOWED_DATE_ASC",
    "NAME_ASC",
    "NAME_DESC",
]


class FollowedCompanyItem(BaseModel):
    company_id: str
    name: str
    industry: Optional[str] = None
    location: Optional[str] = None
    logo: Optional[str] = None
    open_jobs_count: int = 0
    followed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FollowingListResponse(BaseModel):
    items: List[FollowedCompanyItem]
    total: int
    page: int
    page_size: int
    notify_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class FollowActionResponse(BaseModel):
    message: str
    company_id: str
    is_following: bool

    model_config = ConfigDict(from_attributes=True)


class BulkFollowRequest(BaseModel):
    company_ids: List[str] = Field(..., min_length=1, max_length=50)


class BulkFollowResponse(BaseModel):
    followed: List[str]
    already_following: List[str]
    not_found: List[str]

    model_config = ConfigDict(from_attributes=True)


class SuggestedCompany(BaseModel):
    company_id: str
    name: str
    industry: Optional[str] = None
    location: Optional[str] = None
    logo: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SmartSuggestionGroup(BaseModel):
    group_key: str
    title: str
    subtitle: str
    action: Literal["FOLLOW_ALL", "REVIEW"]
    companies: List[SuggestedCompany]

    model_config = ConfigDict(from_attributes=True)


class SmartSuggestionsResponse(BaseModel):
    groups: List[SmartSuggestionGroup]

    model_config = ConfigDict(from_attributes=True)


class NotifyPreferenceUpdate(BaseModel):
    enabled: bool


class NotifyPreferenceResponse(BaseModel):
    notify_enabled: bool

    model_config = ConfigDict(from_attributes=True)