from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CountryResponse(BaseModel):
    country_id: str
    name: str
    iso_code: Optional[str] = None
    phone_code: Optional[str] = None
    currency_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LocationResponse(BaseModel):
    location_id: str
    country_id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class NoticePeriodResponse(BaseModel):
    notice_period_id: str
    label: str

    model_config = ConfigDict(from_attributes=True)


class SalaryExpectationResponse(BaseModel):
    salary_expectation_id: str
    country_id: Optional[str] = None
    label: str

    model_config = ConfigDict(from_attributes=True)


class TargetRoleResponse(BaseModel):
    target_role_id: str
    name: str

    model_config = ConfigDict(from_attributes=True)

class JobCategoryResponse(BaseModel):
    job_category_id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class TimezoneOptionResponse(BaseModel):
    value: str
    label: str


class CountryListResponse(BaseModel):
    items: List[CountryResponse]


class LocationListResponse(BaseModel):
    items: List[LocationResponse]


class NoticePeriodListResponse(BaseModel):
    items: List[NoticePeriodResponse]


class SalaryExpectationListResponse(BaseModel):
    items: List[SalaryExpectationResponse]


class TargetRoleListResponse(BaseModel):
    items: List[TargetRoleResponse]

class JobCategoryListResponse(BaseModel):
    items: List[JobCategoryResponse]


class TimezoneListResponse(BaseModel):
    items: List[TimezoneOptionResponse]
