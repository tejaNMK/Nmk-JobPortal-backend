import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.health import HealthCheckResponse
from app.service.health_service import HealthService


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    responses={
        503: {
            "model": HealthCheckResponse,
            "description": "Application is running but database is unavailable.",
        }
    },
    summary="Application and database health check",
)
async def health_check(session: AsyncSession = Depends(get_db)):
    try:
        await HealthService.check_database(session)
    except Exception as exc:
        logger.exception("Health check database connectivity failed.", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
            },
        )

    return HealthCheckResponse(
        status="healthy",
        database="connected",
    )
