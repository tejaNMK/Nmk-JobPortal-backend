from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from app.utils.utc import utc_now

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.contact_us_model import ContactUsInquiry


class ContactUsRepository:

    @classmethod
    async def create_inquiry(
        cls,
        session: AsyncSession,
        inquiry: ContactUsInquiry,
    ) -> ContactUsInquiry:
        session.add(inquiry)
        await session.commit()
        await session.refresh(inquiry)
        return inquiry

    @classmethod
    async def get_inquiry_by_id(
        cls,
        session: AsyncSession,
        inquiry_id: str,
    ) -> Optional[ContactUsInquiry]:
        result = await session.execute(
            select(ContactUsInquiry).where(
                ContactUsInquiry.inquiry_id == inquiry_id,
                ContactUsInquiry.is_deleted == 0,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def update_email_status(
        cls,
        session: AsyncSession,
        inquiry_id: str,
        email_status: str,
    ) -> bool:
        result = await session.execute(
            sql_update(ContactUsInquiry)
            .where(
                ContactUsInquiry.inquiry_id == inquiry_id,
                ContactUsInquiry.is_deleted == 0,
            )
            .values(
                email_status=email_status,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session="fetch")
        )

        await session.commit()

        return result.rowcount > 0

    @classmethod
    async def increment_retry_count(
        cls,
        session: AsyncSession,
        inquiry_id: str,
    ) -> bool:
        inquiry = await cls.get_inquiry_by_id(
            session=session,
            inquiry_id=inquiry_id,
        )

        if not inquiry:
            return False

        inquiry.retry_count += 1
        inquiry.updated_at = utc_now()

        session.add(inquiry)
        await session.commit()

        return True

    @classmethod
    async def get_failed_inquiries(
        cls,
        session: AsyncSession,
        max_retry_count: int = 3,
    ) -> List[ContactUsInquiry]:

        result = await session.execute(
            select(ContactUsInquiry)
            .where(
                ContactUsInquiry.email_status == "FAILED",
                ContactUsInquiry.retry_count < max_retry_count,
                ContactUsInquiry.is_deleted == 0,
            )
            .order_by(ContactUsInquiry.created_at.asc())
        )

        return list(result.scalars().all())

    @classmethod
    async def soft_delete_inquiry(
        cls,
        session: AsyncSession,
        inquiry_id: str,
    ) -> bool:

        result = await session.execute(
            sql_update(ContactUsInquiry)
            .where(
                ContactUsInquiry.inquiry_id == inquiry_id,
                ContactUsInquiry.is_deleted == 0,
            )
            .values(
                is_deleted=1,
                deleted_at=utc_now(),
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session="fetch")
        )

        await session.commit()

        return result.rowcount > 0
