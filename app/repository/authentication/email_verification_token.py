from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from app.utils.utc import utc_now_naive

from passlib.context import CryptContext
from sqlalchemy import update as sql_update, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.config import commit_rollback
from app.model.authentication.email_verification_token import EmailVerificationToken
from app.repository.authentication.base_repo import BaseRepo


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class EmailVerificationTokenRepository(BaseRepo):
    model = EmailVerificationToken

    @staticmethod
    async def invalidate_active_tokens(session: AsyncSession, email: str) -> None:
        """Invalidate (mark used) active tokens for an email."""
        now = utc_now_naive()
        query = (
            sql_update(EmailVerificationToken)
            .where(EmailVerificationToken.email == email)
            .where(EmailVerificationToken.is_used == False)
            .where(EmailVerificationToken.expires_at > now)
            .values(is_used=True)
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(query)
        await commit_rollback(session)

    @staticmethod
    async def create_token(
        session: AsyncSession,
        *,
        email: str,
        otp_code_hash: str,
        expires_in_minutes: int,
    ) -> EmailVerificationToken:
        # Directly add the record to the session instead of going through
        # BaseRepo.create(), which would call cls.model(**record.dict()) and
        # create a second instance with the same PK. SQLModel's sa_column field
        # declarations can cause kwargs like `otp_hash` to be silently dropped
        # when re-constructed via **kwargs, resulting in a NULL hash in the DB
        # and every subsequent bcrypt.verify() call returning False ("Invalid OTP").
        record = EmailVerificationToken(
            email=email,
            otp_hash=otp_code_hash,
            expires_at=utc_now_naive() + timedelta(minutes=expires_in_minutes),
            verified_at=None,
            is_used=False,
        )
        session.add(record)
        await commit_rollback(session)
        return record

    @staticmethod
    async def find_valid_otp_record(
        session: AsyncSession, *, email: str, plain_otp_code: str
    ) -> Optional[EmailVerificationToken]:
        now = utc_now_naive()
        query = (
            select(EmailVerificationToken)
            .where(EmailVerificationToken.email == email)
            .where(EmailVerificationToken.is_used == False)
            .where(EmailVerificationToken.expires_at > now)
        )
        result = await session.execute(query)
        candidates = result.scalars().all()

        for token_record in candidates:
            if token_record.otp_hash and pwd_context.verify(
                plain_otp_code, token_record.otp_hash
            ):
                return token_record

        return None

    @staticmethod
    async def mark_used_and_verified(
        session: AsyncSession, *, token_id: str
    ) -> None:
        query = (
            sql_update(EmailVerificationToken)
            .where(EmailVerificationToken.id == token_id)
            .values(is_used=True, verified_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )
        await session.execute(query)
        await commit_rollback(session)

    @staticmethod
    async def delete_tokens_by_id(
        session: AsyncSession, *, token_id: str
    ) -> None:
        from sqlalchemy import delete

        await session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.id == token_id)
        )
        await commit_rollback(session)

    @staticmethod
    async def delete_tokens_by_email(session: AsyncSession, *, email: str) -> None:
        from sqlalchemy import delete

        await session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.email == email)
        )
        await commit_rollback(session)

    @staticmethod
    async def find_recently_verified_token(
        session: AsyncSession,
        *,
        email: str,
        within_minutes: int = 30,
    ) -> Optional[EmailVerificationToken]:
        now = utc_now_naive()
        window_start = now - timedelta(minutes=within_minutes)

        query = (
            select(EmailVerificationToken)
            .where(EmailVerificationToken.email == email)
            .where(EmailVerificationToken.verified_at.is_not(None))
            .where(EmailVerificationToken.verified_at >= window_start)
            .where(EmailVerificationToken.is_used == True)
            .order_by(EmailVerificationToken.verified_at.desc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalars().first()

    @staticmethod
    async def get_last_send_time(session: AsyncSession, *, email: str) -> Optional[datetime]:

        """Return created_at of last non-used token for cooldown enforcement."""
        query = (
            select(EmailVerificationToken.created_at)
            .where(EmailVerificationToken.email == email)
            .where(EmailVerificationToken.is_used == False)
            .order_by(EmailVerificationToken.created_at.desc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def find_latest_active_token(
        session: AsyncSession,
        *,
        email: str,
    ) -> Optional[EmailVerificationToken]:


        now = utc_now_naive()

        query = (
            select(EmailVerificationToken)
            .where(EmailVerificationToken.email == email)
            .where(EmailVerificationToken.is_used == False)
            .where(EmailVerificationToken.expires_at > now)
            .order_by(EmailVerificationToken.created_at.desc())
            .limit(1)
        )

        result = await session.execute(query)

        return result.scalars().first()