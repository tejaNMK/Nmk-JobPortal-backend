from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema, success_response
from app.schema.master_data import (
    CountryListResponse,
    JobCategoryListResponse,
    LocationListResponse,
    NoticePeriodListResponse,
    SalaryExpectationListResponse,
    TargetRoleListResponse,
    TimezoneListResponse,
)
from app.service.master_data_service import MasterDataService

router = APIRouter(
    prefix="/master-data",
    tags=["Master Data"],
)

masters_router = APIRouter(
    prefix="/masters",
    tags=["Master Data"],
)


@router.get(
    "/countries",
    response_model=ResponseSchema[CountryListResponse],
    summary="List countries for the Country dropdown",
)
async def get_countries(session: AsyncSession = Depends(get_db)):
    items = await MasterDataService.list_countries(session)
    return success_response(data=CountryListResponse(items=items))


@masters_router.get(
    "/countries",
    response_model=ResponseSchema[CountryListResponse],
    summary="List countries for the Country dropdown",
)
async def get_master_countries(session: AsyncSession = Depends(get_db)):
    return await get_countries(session)


@router.get(
    "/countries/{country_id}/locations",
    response_model=ResponseSchema[LocationListResponse],
    summary="List locations for a country (used for Primary/Preferred Location dropdowns)",
)
async def get_locations_for_country(country_id: str, session: AsyncSession = Depends(get_db)):
    items = await MasterDataService.list_locations(session, country_id)
    return success_response(data=LocationListResponse(items=items))


@masters_router.get(
    "/locations",
    response_model=ResponseSchema[LocationListResponse],
    summary="List locations, optionally filtered by country",
)
async def get_master_locations(
    country_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    items = await MasterDataService.list_locations(session, country_id)
    return success_response(data=LocationListResponse(items=items))


@router.get(
    "/notice-periods",
    response_model=ResponseSchema[NoticePeriodListResponse],
    summary="List Notice Period dropdown options",
)
async def get_notice_periods(session: AsyncSession = Depends(get_db)):
    items = await MasterDataService.list_notice_periods(session)
    return success_response(data=NoticePeriodListResponse(items=items))


@masters_router.get(
    "/notice-periods",
    response_model=ResponseSchema[NoticePeriodListResponse],
    summary="List Notice Period dropdown options",
)
async def get_master_notice_periods(session: AsyncSession = Depends(get_db)):
    return await get_notice_periods(session)


@router.get(
    "/salary-expectations",
    response_model=ResponseSchema[SalaryExpectationListResponse],
    summary="List Salary Expectation dropdown options, optionally scoped by country",
)
async def get_salary_expectations(
    country_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    items = await MasterDataService.list_salary_expectations(session, country_id)
    return success_response(data=SalaryExpectationListResponse(items=items))


@masters_router.get(
    "/salary-ranges",
    response_model=ResponseSchema[SalaryExpectationListResponse],
    summary="List Salary Expectation dropdown options, optionally scoped by country",
)
async def get_master_salary_ranges(
    country_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    return await get_salary_expectations(country_id, session)

@router.get(
    "/job-categories",
    response_model=ResponseSchema[JobCategoryListResponse],
    summary="List Job Category dropdown options",
)
async def get_job_categories(
    session: AsyncSession = Depends(get_db),
):
    items = await MasterDataService.list_job_categories(session)
    return success_response(
        data=JobCategoryListResponse(items=items)
    )


@masters_router.get(
    "/job-categories",
    response_model=ResponseSchema[JobCategoryListResponse],
    summary="List Job Category dropdown options",
)
async def get_master_job_categories(
    session: AsyncSession = Depends(get_db),
):
    return await get_job_categories(session)


@router.get(
    "/timezones",
    response_model=ResponseSchema[TimezoneListResponse],
    summary="List IANA timezone dropdown options",
)
async def get_timezones():
    items = MasterDataService.list_timezones()
    return success_response(data=TimezoneListResponse(items=items))


@masters_router.get(
    "/timezones",
    response_model=ResponseSchema[TimezoneListResponse],
    summary="List IANA timezone dropdown options",
)
async def get_master_timezones():
    return await get_timezones()


@router.get(
    "/target-roles",
    response_model=ResponseSchema[TargetRoleListResponse],
    summary="Search Target Roles (autocomplete, real-time suggestions as the user types)",
)
async def search_target_roles(
    q: Optional[str] = Query(default=None, description="Search text typed by the user"),
    search: Optional[str] = Query(default=None, description="Search text typed by the user"),
    session: AsyncSession = Depends(get_db),
):
    items = await MasterDataService.search_target_roles(session, search or q)
    return success_response(data=TargetRoleListResponse(items=items))


@masters_router.get(
    "/target-roles",
    response_model=ResponseSchema[TargetRoleListResponse],
    summary="Search Target Roles (autocomplete, real-time suggestions as the user types)",
)
async def search_master_target_roles(
    search: Optional[str] = Query(default=None, description="Search text typed by the user"),
    q: Optional[str] = Query(default=None, description="Backward-compatible search text"),
    session: AsyncSession = Depends(get_db),
):
    items = await MasterDataService.search_target_roles(session, search or q)
    return success_response(data=TargetRoleListResponse(items=items))
