from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.contact_us_schema import (
    ContactUsCreateSchema,
    ContactUsResponseSchema,
)

from app.schema.common import (
    ResponseSchema,
    created_response,
    error_response,
)
from app.service.contact_us_service import ContactUsService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/contact-us",
    tags=["Contact Us"],
)


@router.post(
    "",
    response_model=ResponseSchema[ContactUsResponseSchema],
    status_code=201,
)
async def submit_contact_inquiry(
    request: ContactUsCreateSchema,
    session: AsyncSession = Depends(get_db),
):
    """
    Submit a Contact Us inquiry.

    Workflow
    --------
    1. Validate request.
    2. Verify Cloudflare Turnstile.
    3. Store inquiry.
    4. Attempt email delivery.
    5. Return inquiry reference.
    """

    logger.info(
        "Received Contact Us request from %s",
        request.email,
    )

    try:

        response = await ContactUsService.submit_contact_inquiry(
            session=session,
            request=request,
        )

        logger.info(
            "Contact Us inquiry submitted successfully."
        )

        return created_response(
            data=response,
            message="Contact inquiry submitted successfully.",
        )

    except ValueError as exc:

        logger.warning(
            "Contact Us validation failed: %s",
            str(exc),
        )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except HTTPException:

        raise

    except Exception as exc:

        logger.exception(
            "Unexpected error while submitting Contact Us inquiry.",
            exc_info=exc,
        )

        return error_response(
            status=500,
            message="Unable to process your request at this time.",
            code="INTERNAL_SERVER_ERROR",
        )