import asyncio
import logging

from app.config import AsyncSessionLocal
from app.service.authentication.bootstrap_service import ensure_super_admin
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.observability.logging import configure_logging


configure_logging()

logger = logging.getLogger(__name__)


async def main():
    """
    Entry point for one-time Super Admin bootstrap.

    Usage:
        python -m app.bootstrap_super_admin
    """
    try:
        bootstrap_mappers() 
        async with AsyncSessionLocal() as session:
            result = await ensure_super_admin(session)

        if result:
            logger.info(
                "Super Admin bootstrap completed",
                extra={"event": "super_admin_bootstrap_completed"},
            )

    except Exception:
        logger.exception("Super Admin bootstrap failed.")
        raise


if __name__ == "__main__":
    asyncio.run(main())
