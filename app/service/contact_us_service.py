
from __future__ import annotations

import logging
from typing import Final, Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    TURNSTILE_SECRET_KEY,
    TURNSTILE_VERIFY_URL,
)
from app.model.contact_us_model import ContactUsInquiry
from app.repository.contact_us_repo import ContactUsRepository
from app.service.authentication.email_service import EmailService
from app.schema.contact_us_schema import (
    ContactUsCreateSchema,
    ContactUsResponseSchema,
)

logger = logging.getLogger(__name__)


class ContactUsService:


    EMAIL_STATUS_PENDING: Final[str] = "PENDING"
    EMAIL_STATUS_SENT: Final[str] = "SENT"
    EMAIL_STATUS_FAILED: Final[str] = "FAILED"

    import os
    MAX_RETRY_COUNT: Final[int] = int(
        os.getenv("CONTACT_US_MAX_RETRY_COUNT", "3")
    )

    SUBJECT_MAPPING: Final[dict[str, str]] = {
        "JOB_SEEKER_SUPPORT": "Job Seeker Support",
        "EMPLOYER_SUPPORT": "Employer Support",
        "TECHNICAL_ISSUE": "Technical Issue",
        "GENERAL_QUERY": "General Query",
    }

    @classmethod
    async def verify_turnstile(
        cls,
        token: str,
    ) -> None:
        

        if not TURNSTILE_SECRET_KEY or not TURNSTILE_SECRET_KEY.strip():
            logger.error(
                "Cloudflare Turnstile verification unavailable: secret is not configured."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            )
            

        try:

            async with httpx.AsyncClient(timeout=15) as client:

                response = await client.post(
                    TURNSTILE_VERIFY_URL,
                    data={
                        "secret": TURNSTILE_SECRET_KEY,
                        "response": token,
                    },
                )

            response.raise_for_status()

            payload = response.json()

        except httpx.TimeoutException as exc:

            logger.warning(
                "Cloudflare Turnstile verification unavailable: upstream timeout."
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            ) from exc

        except httpx.RequestError as exc:

            logger.warning(
                "Cloudflare Turnstile verification unavailable: upstream request failed."
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            ) from exc

        except httpx.HTTPStatusError as exc:

            logger.warning(
                "Cloudflare Turnstile verification unavailable: upstream returned HTTP %s.",
                exc.response.status_code if exc.response is not None else "unknown",
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            ) from exc

        except ValueError as exc:

            logger.warning(
                "Cloudflare Turnstile verification unavailable: malformed upstream response."
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "Cloudflare Turnstile verification unavailable: unexpected upstream response."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CAPTCHA verification service is unavailable.",
            )

        cls._validate_turnstile_response(
            payload,
        )

        logger.info(
            "Cloudflare Turnstile verification successful."
        )

    @classmethod
    def _build_subject(
        cls,
        inquiry_type: str,
        custom_subject: str | None,
    ) -> str:


        if inquiry_type == "OTHER":
            return (
                custom_subject.strip()
                if custom_subject
                else "General Inquiry"
            )

        return cls.SUBJECT_MAPPING.get(
            inquiry_type,
            inquiry_type.replace("_", " ").title(),
        ) 

    @classmethod
    def _build_inquiry(
        cls,
        request: ContactUsCreateSchema,
    ) -> ContactUsInquiry:


        return ContactUsInquiry(
            full_name=request.full_name,
            email=request.email,
            phone_number=request.phone_number,
            inquiry_type=request.inquiry_type,
            custom_subject=request.custom_subject,
            message=request.message,
            email_status=cls.EMAIL_STATUS_PENDING,
            retry_count=0,
        )
    
    @classmethod
    async def _save_inquiry(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> ContactUsInquiry:


        logger.info(
            "Saving Contact Us inquiry for email=%s",
            inquiry.email,
        )

        saved_inquiry = await ContactUsRepository.create_inquiry(
            session=session,
            inquiry=inquiry,
        )

        logger.info(
            "Inquiry %s saved successfully.",
            saved_inquiry.inquiry_id,
        )

        return saved_inquiry

    @classmethod
    async def _mark_email_sent(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> None:

        logger.info(
            "Updating inquiry %s email status to SENT.",
            inquiry.inquiry_id,
        )

        await ContactUsRepository.update_email_status(
            session=session,
            inquiry_id=inquiry.inquiry_id,
            email_status=cls.EMAIL_STATUS_SENT,
        )

        inquiry.email_status = cls.EMAIL_STATUS_SENT

    @classmethod
    async def _mark_email_failed(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> None:


        logger.warning(
            "Updating inquiry %s email status to FAILED.",
            inquiry.inquiry_id,
        )

        await ContactUsRepository.update_email_status(
            session=session,
            inquiry_id=inquiry.inquiry_id,
            email_status=cls.EMAIL_STATUS_FAILED,
        )

        inquiry.email_status = cls.EMAIL_STATUS_FAILED

    @classmethod
    async def _increment_retry_count(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> None:


        logger.info(
            "Incrementing retry count for inquiry %s",
            inquiry.inquiry_id,
        )

        await ContactUsRepository.increment_retry_count(
            session=session,
            inquiry_id=inquiry.inquiry_id,
        )

        inquiry.retry_count += 1

    @classmethod
    async def _mark_failed_and_increment_retry(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> None:


        logger.info(
            "Updating inquiry %s after email failure.",
            inquiry.inquiry_id,
        )

        await cls._mark_email_failed(
            session=session,
            inquiry=inquiry,
        )

        await cls._increment_retry_count(
            session=session,
            inquiry=inquiry,
        )

    @classmethod
    async def _get_failed_inquiries(
        cls,
        session: AsyncSession,
    ) -> list[ContactUsInquiry]:


        logger.info(
            "Fetching failed Contact Us inquiries for retry."
        )

        return await ContactUsRepository.get_failed_inquiries(
            session=session,
            max_retry_count=cls.MAX_RETRY_COUNT,
        )

    @classmethod
    def _build_response(
        cls,
        inquiry: ContactUsInquiry,
    ) -> ContactUsResponseSchema:


        return ContactUsResponseSchema(
            inquiry_id=inquiry.inquiry_id,
            email_status=inquiry.email_status,
        )
    
    
    @classmethod
    async def _send_support_email(
        cls,
        inquiry: ContactUsInquiry,
        subject: str,
    ) -> None:


        logger.info(
            "Sending support email for inquiry %s",
            inquiry.inquiry_id,
        )

        await EmailService.send_contact_support_email(
            inquiry_id=inquiry.inquiry_id,
            full_name=inquiry.full_name,
            email=inquiry.email,
            phone_number=inquiry.phone_number,
            inquiry_type=inquiry.inquiry_type,
            subject=subject,
            message=inquiry.message,
        )

        logger.info(
            "Support email sent successfully for inquiry %s",
            inquiry.inquiry_id,
        )

    @classmethod
    async def _send_acknowledgement_email(
        cls,
        inquiry: ContactUsInquiry,
        subject: str,
    ) -> None:


        logger.info(
            "Sending acknowledgement email for inquiry %s",
            inquiry.inquiry_id,
        )

        await EmailService.send_contact_acknowledgement_email(
            inquiry_id=inquiry.inquiry_id,
            full_name=inquiry.full_name,
            email=inquiry.email,
            subject=subject,
            message=inquiry.message,
        )

        logger.info(
            "Acknowledgement email sent successfully for inquiry %s",
            inquiry.inquiry_id,
        )


    @classmethod
    async def _send_inquiry_emails(
        cls,
        inquiry: ContactUsInquiry,
    ) -> None:

        subject = cls._build_subject(
            inquiry.inquiry_type,
            inquiry.custom_subject,
        )

        logger.info(
            "Sending Contact Us emails for inquiry %s",
            inquiry.inquiry_id,
        )

        await cls._send_support_email(
            inquiry=inquiry,
            subject=subject,
        )

        await cls._send_acknowledgement_email(
            inquiry=inquiry,
            subject=subject,
        )

        logger.info(
            "Completed email delivery for inquiry %s",
            inquiry.inquiry_id,
        )

    @classmethod
    async def _process_email_delivery(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> None:


        try:

            await cls._send_inquiry_emails(
                inquiry=inquiry,
            )

            await cls._mark_email_sent(
                session=session,
                inquiry=inquiry,
            )

            logger.debug(
                "Switching inquiry %s to failure workflow.",
                inquiry.inquiry_id,
            )

        except Exception as exc:

            await cls._safe_mark_failed(
                session=session,
                inquiry=inquiry,
                exception=exc,
            )
    
    @classmethod
    async def submit_contact_inquiry(
        cls,
        *,
        session: AsyncSession,
        request: ContactUsCreateSchema,
    ) -> ContactUsResponseSchema:


        logger.info(
            "Received Contact Us inquiry from '%s'.",
            request.email,
        )

        await cls.verify_turnstile(
            request.turnstile_token,
        )

        inquiry = cls._build_inquiry(
            request,
        )

        inquiry = await cls._save_inquiry(
            session=session,
            inquiry=inquiry,
        )

        logger.info(
            "Inquiry created with ID %s",
            inquiry.inquiry_id,
        )

        await cls._process_email_delivery(
            session=session,
            inquiry=inquiry,
        )

        logger.info(
            "Completed Contact Us workflow for inquiry %s",
            inquiry.inquiry_id,
        )

        return cls._build_response(
            inquiry,
        )
    
    @classmethod
    async def retry_failed_inquiries(
        cls,
        *,
        session: AsyncSession,
    ) -> None:


        logger.info(
            "Starting Contact Us email retry process."
        )

        failed_inquiries = await cls._get_failed_inquiries(
            session=session,
        )

        if not failed_inquiries:

            logger.info(
                "No failed Contact Us inquiries found."
            )

            return

        logger.info(
            "Found %s failed inquiries.",
            len(failed_inquiries),
        )

        success_count = 0
        failed_count = 0

        for inquiry in failed_inquiries:

            if not cls._is_retry_allowed(inquiry):

                logger.info(
                    "Skipping inquiry %s because retry limit has been reached.",
                    inquiry.inquiry_id,
                )

                continue

            logger.info(
                "Retrying inquiry %s",
                inquiry.inquiry_id,
            )

            try:

                await cls._send_inquiry_emails(
                    inquiry=inquiry,
                )

                await cls._mark_email_sent(
                    session=session,
                    inquiry=inquiry,
                )

                success_count += 1

                logger.info(
                    "Retry successful for inquiry %s",
                    inquiry.inquiry_id,
                )

            except Exception as exc:

                await cls._safe_mark_retry_failed(
                    session=session,
                    inquiry=inquiry,
                    exception=exc,
                )

                failed_count += 1

        logger.info(
            (
                "Retry process completed. "
                "Success=%s Failed=%s"
            ),
            success_count,
            failed_count,
        )

    @staticmethod
    def _log_email_failure(
        inquiry_id: str,
        exception: Exception,
    ) -> None:
       

        logger.exception(
            "Email delivery failed for inquiry %s",
            inquiry_id,
            exc_info=exception,
        )

    @staticmethod
    def _log_retry_failure(
        inquiry_id: str,
        exception: Exception,
    ) -> None:


        logger.exception(
            "Retry failed for inquiry %s",
            inquiry_id,
            exc_info=exception,
        )

    @staticmethod
    def _log_turnstile_failure(
        errors: object,
    ) -> None:


        logger.warning(
            "Cloudflare Turnstile validation failed. Errors=%s",
            errors,
        )

    @classmethod
    def _validate_turnstile_response(
        cls,
        payload: dict[str, Any],
    ) -> None:

        if payload.get("success"):
            return

        cls._log_turnstile_failure(
            payload.get("error-codes"),
        )

        raise ValueError(
            "Captcha validation failed."
        )

    @classmethod
    async def _safe_mark_failed(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
        exception: Exception,
    ) -> None:


        cls._log_email_failure(
            inquiry.inquiry_id,
            exception,
        )

        logger.warning(
            "Marking inquiry %s as FAILED.",
            inquiry.inquiry_id,
        )

        try:

            await cls._mark_failed_and_increment_retry(
                session=session,
                inquiry=inquiry,
            )

        except Exception as db_exception:

            logger.exception(
                "Unable to update failure status for inquiry %s",
                inquiry.inquiry_id,
                exc_info=db_exception,
            )

    @classmethod
    async def _safe_mark_retry_failed(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
        exception: Exception,
    ) -> None:


        cls._log_retry_failure(
            inquiry.inquiry_id,
            exception,
        )

        logger.warning(
            "Incrementing retry count for inquiry %s.",
            inquiry.inquiry_id,
        )

        try:

            await cls._increment_retry_count(
                session=session,
                inquiry=inquiry,
            )

        except Exception as db_exception:

            logger.exception(
                "Unable to increment retry count for inquiry %s",
                inquiry.inquiry_id,
                exc_info=db_exception,
            )

    @staticmethod
    def health_check() -> dict:


        return {
            "service": "ContactUsService",
            "status": "UP",
        }
    
    @staticmethod
    def _is_retry_allowed(
        inquiry: ContactUsInquiry,
    ) -> bool:

        return (
            inquiry.email_status
            == ContactUsService.EMAIL_STATUS_FAILED
            and inquiry.retry_count
            < ContactUsService.MAX_RETRY_COUNT
        )

    @staticmethod
    def _is_email_sent(
        inquiry: ContactUsInquiry,
    ) -> bool:


        return (
            inquiry.email_status
            == ContactUsService.EMAIL_STATUS_SENT
        )

    @staticmethod
    def _build_inquiry_summary(
        inquiry: ContactUsInquiry,
    ) -> dict:


        return {
            "inquiry_id": inquiry.inquiry_id,
            "full_name": inquiry.full_name,
            "email": inquiry.email,
            "inquiry_type": inquiry.inquiry_type,
            "email_status": inquiry.email_status,
            "retry_count": inquiry.retry_count,
        }

    @classmethod
    def _validate_email_status(
        cls,
        status: str,
    ) -> None:


        allowed_statuses = {
            cls.EMAIL_STATUS_PENDING,
            cls.EMAIL_STATUS_SENT,
            cls.EMAIL_STATUS_FAILED,
        }

        if status not in allowed_statuses:

            raise ValueError(
                f"Invalid email status '{status}'."
            )

    @classmethod
    async def get_service_statistics(
        cls,
        session: AsyncSession,
    ) -> dict:


        failed = await ContactUsRepository.get_failed_inquiries(
            session=session,
            max_retry_count=cls.MAX_RETRY_COUNT,
        )

        return {
            "failed_email_count": len(failed),
            "max_retry_count": cls.MAX_RETRY_COUNT,
            "service": "ContactUsService",
        }
    
