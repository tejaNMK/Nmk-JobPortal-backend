from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy
from app.utils.utc import utc_now_naive
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.authentication.user_session import UserSession


class UserSessionRepository:

    @staticmethod
    async def create_session(
        session: AsyncSession,
        user_id: str,
        jwt_id: str,
        login_method: str = "EMAIL",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> UserSession:

        user_session = UserSession(
            user_id=UUID(user_id),
            jwt_id=jwt_id,
            login_method=login_method,
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type,
            session_status="ACTIVE",
            login_at=utc_now_naive(),
        )

        session.add(user_session)

        await commit_rollback(session)

        return user_session

    @staticmethod
    async def find_active_session_by_jwt_id(
        session: AsyncSession,
        jwt_id: str,
    ) -> Optional[UserSession]:

        query = select(UserSession).where(
            UserSession.jwt_id == jwt_id,
            UserSession.session_status == "ACTIVE",
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def logout_session(
        session: AsyncSession,
        jwt_id: str,
    ) -> bool:

        stmt = (
            sqlalchemy.update(UserSession)
            .where(
                UserSession.jwt_id == jwt_id,
                UserSession.session_status == "ACTIVE",
            )
            .values(
                session_status="LOGGED_OUT",
                logout_at=utc_now_naive(),
            )
            .execution_options(synchronize_session="fetch")
        )

        result = await session.execute(stmt)

        await commit_rollback(session)

        return result.rowcount > 0

    @staticmethod
    async def logout_all_sessions(
        session: AsyncSession,
        user_id: str,
    ) -> int:


        stmt = (
            sqlalchemy.update(UserSession)
            .where(
                UserSession.user_id == UUID(user_id),
                UserSession.session_status == "ACTIVE",
            )
            .values(
                session_status="LOGGED_OUT",
                logout_at=utc_now_naive(),
            )
            .execution_options(synchronize_session="fetch")
        )

        result = await session.execute(stmt)

        await commit_rollback(session)

        return result.rowcount