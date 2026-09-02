from typing import List
from uuid import UUID
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.authentication.user_role import UsersRole
from app.repository.authentication.base_repo import BaseRepo


class UsersRoleRepository(BaseRepo):

    model = UsersRole

    @staticmethod
    async def find_by_user_id(
        session: AsyncSession,
        user_id: UUID,
    ):
        query = select(UsersRole).where(UsersRole.user_id == user_id)
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def find_user_role(
        session: AsyncSession,
        user_id: UUID,
        role_id: UUID,
    ):
        query = select(UsersRole).where(
            UsersRole.user_id == user_id,
            UsersRole.role_id == role_id,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def assign_role(
        session: AsyncSession,
        user_id: UUID,
        role_id: UUID,
    ):
        existing_role = await UsersRoleRepository.find_user_role(
            session,
            user_id,
            role_id,
        )

        if existing_role:
            return existing_role

        user_role = UsersRole(
            user_id=user_id,
            role_id=role_id,
            assigned_at=utc_now_naive(),
        )

        session.add(user_role)
        await commit_rollback(session)

        return user_role
