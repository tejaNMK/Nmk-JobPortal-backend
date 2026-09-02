from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import commit_rollback
from app.model.authentication.role import Role
from app.repository.authentication.base_repo import BaseRepo


class RoleRepository(BaseRepo):
    model = Role

    # =========================
    # FIND BY ROLE NAME
    # =========================
    @staticmethod
    async def find_by_role_name(session: AsyncSession, role_name: str):
        query = select(Role).where(Role.role_name == role_name)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    # =========================
    # FIND BY ROLE CODE
    # =========================
    @staticmethod
    async def find_by_role_code(session: AsyncSession, role_code: str | None = None):

        if role_code is None:
            return None
        query = select(Role).where(Role.role_code == role_code)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    # =========================
    # FIND BY ROLE CODES
    # =========================
    @staticmethod
    async def find_by_role_codes(session: AsyncSession, role_codes: List[str]):
        query = select(Role).where(Role.role_code.in_(role_codes))
        result = await session.execute(query)
        return result.scalars().all()

    # =========================
    # CREATE MULTIPLE ROLES
    # =========================
    @staticmethod
    async def create_list(session: AsyncSession, roles: List[dict]):
        role_objects = [Role(**role_data) for role_data in roles]
        session.add_all(role_objects)
        await commit_rollback(session)
        return role_objects

