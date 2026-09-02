from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.employer_profile import EmployerProfile


async def get_existing_employer_profile(
    session: AsyncSession,
    payload: dict,
) -> EmployerProfile:
    query = select(EmployerProfile).where(EmployerProfile.user_id == payload.get("user_id"))
    result = await session.execute(query)
    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(status_code=403, detail="Employer profile not found")
    return employer
