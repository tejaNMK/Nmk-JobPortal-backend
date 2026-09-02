from sqlalchemy import update as sql_update, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.authentication.users import Users
from app.repository.authentication.base_repo import BaseRepo


class UsersRepository(BaseRepo):  

    model = Users

    # =========================
    # FIND BY EMAIL
    # =========================
    @staticmethod
    async def find_by_email(session: AsyncSession, email: str):

        query = (
            select(Users)
            .options(selectinload(Users.roles))
            .where(Users.email == email)
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    # =========================
    # FIND BY MOBILE
    # =========================
    @staticmethod
    async def find_by_mobile(session: AsyncSession, mobile_number: str):

        query = (
            select(Users)
            .options(selectinload(Users.roles))
            .where(Users.mobile_number == mobile_number)
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    # =========================
    # FIND BY USER ID
    # =========================
    @staticmethod
    async def find_by_user_id(session: AsyncSession, user_id: str):

        query = (
            select(Users)
            .options(selectinload(Users.roles))
            .where(Users.user_id == user_id)
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    # =========================
    # UPDATE PASSWORD
    # =========================
    @staticmethod
    async def update_password(
        session: AsyncSession,
        email: str,
        password_hash: str,
    ):

        query = (
            sql_update(Users)
            .where(Users.email == email)
            .values(
                password_hash=password_hash
            )
            .execution_options(
                synchronize_session="fetch"
            )
        )

        await session.execute(query)

        await commit_rollback(session)

    # =========================
    # UPDATE LAST LOGIN
    # =========================
    @staticmethod
    async def update_last_login(session: AsyncSession, user_id: str):

        query = (
            sql_update(Users)
            .where(Users.user_id == user_id)
            .values(
                last_login_at=func.now()
            )
            .execution_options(
                synchronize_session="fetch"
            )
        )

        await session.execute(query)
        await commit_rollback(session)
