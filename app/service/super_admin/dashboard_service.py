from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.super_admin.dashboard_repo import DashboardRepository
from app.schema.super_admin.dashboard import DashboardSummaryResponse
from app.utils.date_range import NormalizedDateRange


class DashboardService:

    @staticmethod
    async def get_dashboard_summary(
        session: AsyncSession,
        date_range: NormalizedDateRange | None = None,
    ) -> DashboardSummaryResponse:

        data = await DashboardRepository.get_dashboard_summary(
            session=session,
            date_range=date_range,
        )

        return DashboardSummaryResponse(**data)
