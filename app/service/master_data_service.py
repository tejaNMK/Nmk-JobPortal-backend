from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.master_data_repo import MasterDataRepo
from app.schema.master_data import (
    CountryResponse,
    JobCategoryResponse,
    LocationResponse,
    NoticePeriodResponse,
    SalaryExpectationResponse,
    TimezoneOptionResponse,
    TargetRoleResponse,
)
from app.utils.timezones import get_timezone_options

MAX_TARGET_ROLES = 5


class MasterDataService:

    # ── Read / list endpoints ────────────────────────────────────────────
    @staticmethod
    async def list_countries(session: AsyncSession) -> List[CountryResponse]:
        rows = await MasterDataRepo.list_countries(session)
        return [CountryResponse.model_validate(r) for r in rows]

    @staticmethod
    async def list_locations(session: AsyncSession, country_id: Optional[str] = None) -> List[LocationResponse]:
        if country_id:
            country = await MasterDataRepo.get_country(session, country_id)
            if not country:
                raise HTTPException(status_code=404, detail="Country not found")
        rows = await MasterDataRepo.list_locations(session, country_id)
        return [LocationResponse.model_validate(r) for r in rows]

    @staticmethod
    async def list_notice_periods(session: AsyncSession) -> List[NoticePeriodResponse]:
        rows = await MasterDataRepo.list_notice_periods(session)
        return [NoticePeriodResponse.model_validate(r) for r in rows]

    @staticmethod
    async def list_salary_expectations(
        session: AsyncSession, country_id: Optional[str] = None
    ) -> List[SalaryExpectationResponse]:
        if country_id:
            country = await MasterDataRepo.get_country(session, country_id)
            if not country:
                raise HTTPException(status_code=404, detail="Country not found")
        rows = await MasterDataRepo.list_salary_expectations(session, country_id)
        return [SalaryExpectationResponse.model_validate(r) for r in rows]

    @staticmethod
    async def list_job_categories(
        session: AsyncSession,
    ) -> List[JobCategoryResponse]:
        rows = await MasterDataRepo.list_job_categories(session)
        return [
            JobCategoryResponse.model_validate(row)
            for row in rows
        ]

    @staticmethod
    def list_timezones() -> List[TimezoneOptionResponse]:
        return [
            TimezoneOptionResponse(**option)
            for option in get_timezone_options()
        ]

    @staticmethod
    async def validate_job_category(
        session: AsyncSession,
        job_category: str,
    ):
        category = await MasterDataRepo.get_job_category(
            session,
            job_category,
        )

        if not category:
            raise HTTPException(
                status_code=400,
                detail="Invalid Job Category selected",
            )

        return category
    
    @staticmethod
    async def search_target_roles(session: AsyncSession, query: Optional[str]) -> List[TargetRoleResponse]:
        rows = await MasterDataRepo.search_target_roles(session, query)
        return [TargetRoleResponse.model_validate(r) for r in rows]

    # ── Validation helpers used by candidate profile updates ────────────
    @staticmethod
    async def validate_country(session: AsyncSession, country_id: str):
        country = await MasterDataRepo.get_country(session, country_id)
        if not country:
            raise HTTPException(status_code=400, detail="Invalid country selected")
        return country

    @staticmethod
    async def validate_location_for_country(session: AsyncSession, location_id: str, country_id: Optional[str]):
        location = await MasterDataRepo.get_location(session, location_id)
        if not location:
            raise HTTPException(status_code=400, detail="Invalid location selected")
        if country_id and location.country_id != country_id:
            raise HTTPException(status_code=400, detail="Selected location does not belong to the selected country")
        return location

    @staticmethod
    async def validate_notice_period(session: AsyncSession, notice_period_id: str):
        notice_period = await MasterDataRepo.get_notice_period(session, notice_period_id)
        if not notice_period:
            raise HTTPException(status_code=400, detail="Invalid notice period selected")
        return notice_period

    @staticmethod
    async def validate_salary_expectation(session: AsyncSession, salary_expectation_id: str):
        salary_expectation = await MasterDataRepo.get_salary_expectation(session, salary_expectation_id)
        if not salary_expectation:
            raise HTTPException(status_code=400, detail="Invalid salary expectation selected")
        return salary_expectation

    @staticmethod
    async def resolve_target_roles(
        session: AsyncSession,
        target_role_ids: Optional[List[str]],
        target_role_names: Optional[List[str]],
    ) -> List[str]:
        
        resolved_ids: List[str] = []

        if target_role_ids:
            roles = await MasterDataRepo.get_target_roles_by_ids(session, target_role_ids)
            found_ids = {r.target_role_id for r in roles}
            missing = [rid for rid in target_role_ids if rid not in found_ids]
            if missing:
                raise HTTPException(status_code=400, detail=f"Invalid target role(s): {missing}")
            resolved_ids.extend(found_ids)

        if target_role_names:
            for name in target_role_names:
                if not name or not name.strip():
                    continue
                role = await MasterDataRepo.get_or_create_target_role_by_name(session, name)
                resolved_ids.append(role.target_role_id)

        deduped_ids = list(dict.fromkeys(resolved_ids))
        if len(deduped_ids) > MAX_TARGET_ROLES:
            raise HTTPException(status_code=400, detail=f"You can select at most {MAX_TARGET_ROLES} target roles")

        return deduped_ids
