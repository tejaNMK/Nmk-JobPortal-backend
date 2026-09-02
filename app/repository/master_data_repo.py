from typing import List, Optional, Sequence

from sqlalchemy import delete as sql_delete
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.master_data.country import MasterCountry
from app.model.master_data.location import MasterLocation
from app.model.master_data.notice_period import MasterNoticePeriod
from app.model.master_data.salary_expectation import MasterSalaryExpectation
from app.model.master_data.target_role import MasterTargetRole
from app.model.master_data.candidate_target_role import CandidateTargetRole
from app.model.master_data.job_category import MasterJobCategory


class MasterDataRepo:

    # ── Countries ────────────────────────────────────────────────────────
    @classmethod
    async def list_countries(cls, session: AsyncSession) -> Sequence[MasterCountry]:
        result = await session.execute(
            select(MasterCountry)
            .where(MasterCountry.is_active.is_(True))
            .order_by(MasterCountry.sort_order, MasterCountry.name)
        )
        return result.scalars().all()

    @classmethod
    async def get_country(cls, session: AsyncSession, country_id: str) -> Optional[MasterCountry]:
        result = await session.execute(
            select(MasterCountry).where(
                MasterCountry.country_id == country_id,
                MasterCountry.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ── Locations (dependent on country) ────────────────────────────────
    @classmethod
    async def list_locations(cls, session: AsyncSession, country_id: Optional[str] = None) -> Sequence[MasterLocation]:
        stmt = select(MasterLocation).where(MasterLocation.is_active.is_(True))
        if country_id:
            stmt = stmt.where(MasterLocation.country_id == country_id)
        result = await session.execute(stmt.order_by(MasterLocation.sort_order, MasterLocation.name))
        return result.scalars().all()

    @classmethod
    async def get_location(cls, session: AsyncSession, location_id: str) -> Optional[MasterLocation]:
        result = await session.execute(
            select(MasterLocation).where(
                MasterLocation.location_id == location_id,
                MasterLocation.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ── Notice periods ───────────────────────────────────────────────────
    @classmethod
    async def list_notice_periods(cls, session: AsyncSession) -> Sequence[MasterNoticePeriod]:
        result = await session.execute(
            select(MasterNoticePeriod)
            .where(MasterNoticePeriod.is_active.is_(True))
            .order_by(MasterNoticePeriod.sort_order, MasterNoticePeriod.label)
        )
        return result.scalars().all()

    @classmethod
    async def get_notice_period(cls, session: AsyncSession, notice_period_id: str) -> Optional[MasterNoticePeriod]:
        result = await session.execute(
            select(MasterNoticePeriod).where(
                MasterNoticePeriod.notice_period_id == notice_period_id,
                MasterNoticePeriod.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ── Salary expectations (optionally scoped by country) ──────────────
    @classmethod
    async def list_salary_expectations(
        cls, session: AsyncSession, country_id: Optional[str] = None
    ) -> Sequence[MasterSalaryExpectation]:
        # If a country has its own dedicated bands (e.g. India's LPA
        # ranges), use those. Otherwise fall back to the country-agnostic
        # default bands (country_id IS NULL, e.g. "$50K - $70K") -- this is
        # what previously made every country, including the US, show
        # India's LPA bands: there was no fallback and no country scoping
        # at all, so the single global list (LPA) was used for everyone.
        if country_id:
            result = await session.execute(
                select(MasterSalaryExpectation)
                .where(
                    MasterSalaryExpectation.is_active.is_(True),
                    MasterSalaryExpectation.country_id == country_id,
                )
                .order_by(MasterSalaryExpectation.sort_order, MasterSalaryExpectation.label)
            )
            rows = result.scalars().all()
            if rows:
                return rows

        result = await session.execute(
            select(MasterSalaryExpectation)
            .where(
                MasterSalaryExpectation.is_active.is_(True),
                MasterSalaryExpectation.country_id.is_(None),
            )
            .order_by(MasterSalaryExpectation.sort_order, MasterSalaryExpectation.label)
        )
        return result.scalars().all()

    @classmethod
    async def get_salary_expectation(cls, session: AsyncSession, salary_expectation_id: str) -> Optional[MasterSalaryExpectation]:
        result = await session.execute(
            select(MasterSalaryExpectation).where(
                MasterSalaryExpectation.salary_expectation_id == salary_expectation_id,
                MasterSalaryExpectation.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
    
    # ── Job Categories ──────────────────────────────────────────────
    @classmethod
    async def list_job_categories(
        cls,
        session: AsyncSession,
    ) -> Sequence[MasterJobCategory]:
        result = await session.execute(
            select(MasterJobCategory)
            .where(MasterJobCategory.is_active.is_(True))
            .order_by(
                MasterJobCategory.sort_order,
                MasterJobCategory.name,
            )
        )
        return result.scalars().all()


    @classmethod
    async def get_job_category(
        cls,
        session: AsyncSession,
        job_category: str,
    ) -> Optional[MasterJobCategory]:
        result = await session.execute(
            select(MasterJobCategory).where(
                MasterJobCategory.name.ilike(job_category.strip()),
                MasterJobCategory.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ── Target roles (search/autocomplete) ──────────────────────────────
    @classmethod
    async def search_target_roles(cls, session: AsyncSession, query: Optional[str], limit: int = 20) -> Sequence[MasterTargetRole]:
        stmt = select(MasterTargetRole).where(MasterTargetRole.is_active.is_(True))
        if query:
            stmt = stmt.where(MasterTargetRole.name.ilike(f"%{query.strip()}%"))
        stmt = stmt.order_by(MasterTargetRole.name).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_target_roles_by_ids(cls, session: AsyncSession, target_role_ids: List[str]) -> Sequence[MasterTargetRole]:
        if not target_role_ids:
            return []
        result = await session.execute(
            select(MasterTargetRole).where(
                MasterTargetRole.target_role_id.in_(target_role_ids),
                MasterTargetRole.is_active.is_(True),
            )
        )
        return result.scalars().all()

    @classmethod
    async def get_or_create_target_role_by_name(cls, session: AsyncSession, name: str) -> MasterTargetRole:
        clean = name.strip()
        result = await session.execute(
            select(MasterTargetRole).where(MasterTargetRole.name.ilike(clean))
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        role = MasterTargetRole(name=clean)
        session.add(role)
        await session.flush()
        return role

    # ── Candidate <-> target role links ─────────────────────────────────
    @classmethod
    async def get_candidate_target_roles(cls, session: AsyncSession, candidate_id: str) -> Sequence[MasterTargetRole]:
        result = await session.execute(
            select(MasterTargetRole)
            .join(CandidateTargetRole, CandidateTargetRole.target_role_id == MasterTargetRole.target_role_id)
            .where(CandidateTargetRole.candidate_id == candidate_id)
            .order_by(MasterTargetRole.name)
        )
        return result.scalars().all()

    @classmethod
    async def replace_candidate_target_roles(cls, session: AsyncSession, candidate_id: str, target_role_ids: List[str]) -> None:
        """Overwrite the full set of target roles linked to a candidate."""
        await session.execute(
            sql_delete(CandidateTargetRole).where(CandidateTargetRole.candidate_id == candidate_id)
        )
        for role_id in dict.fromkeys(target_role_ids):  # de-dupe, preserve order
            session.add(CandidateTargetRole(candidate_id=candidate_id, target_role_id=role_id))
        await session.commit()