from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthService:
    @staticmethod
    async def check_database(session: AsyncSession) -> None:
        await session.execute(text("SELECT 1"))
