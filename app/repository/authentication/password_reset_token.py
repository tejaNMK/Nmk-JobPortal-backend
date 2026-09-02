from sqlalchemy import update as sql_update, select
from datetime import datetime, timedelta
from app.utils.utc import utc_now_naive
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import commit_rollback
from app.model.authentication.password_reset_token import PasswordResetToken
from app.repository.authentication.base_repo import BaseRepo

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class PasswordResetTokenRepository(BaseRepo):


    model = PasswordResetToken

    # =========================
    # CREATE RESET TOKEN
    # =========================
    @staticmethod
    async def create_reset_token(
        session: AsyncSession,
        user_id: str,
        reset_token_hash: str = None,
        otp_code_hash: str = None,
        expires_in_minutes: int = 60
    ):
        token = PasswordResetToken(
            user_id=user_id,
            reset_token_hash=reset_token_hash,
            otp_code_hash=otp_code_hash,
            expires_at=utc_now_naive() + timedelta(minutes=expires_in_minutes),
            used_flag=False
        )

        created_token = await PasswordResetTokenRepository.create(
            session=session,
            **token.dict()
        )

        return created_token


    # =========================
    # FIND VALID TOKEN
    # =========================
    @staticmethod
    async def find_valid_otp_by_user_and_code(session: AsyncSession, user_id: str, plain_otp_code: str):

        # First get all unused, non-expired otp records for this user

        query = (
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .where(PasswordResetToken.used_flag == False)
            .where(PasswordResetToken.expires_at > utc_now_naive())
        )


        result = await session.execute(query)
        tokens = result.scalars().all()


        # Verify the plain otp code against each hashed otp
        for token_record in tokens:
            if token_record.otp_code_hash and pwd_context.verify(plain_otp_code, token_record.otp_code_hash):
                return token_record


        return None

    @staticmethod
    async def find_latest_active_token(
        session: AsyncSession,
        user_id: str,
    ):


        query = (
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .where(PasswordResetToken.used_flag == False)
            .where(PasswordResetToken.expires_at > utc_now_naive())
            .order_by(PasswordResetToken.created_at.desc())
            .limit(1)
        )

        result = await session.execute(query)
        return result.scalars().first()

    # =========================
    # MARK TOKEN AS USED
    # =========================
    @staticmethod
    async def mark_token_as_used(session: AsyncSession, token_id: str):

        query = (
            sql_update(PasswordResetToken)
            .where(PasswordResetToken.token_id == token_id)
            .values(used_flag=True)
            .execution_options(synchronize_session="fetch")
        )

        await session.execute(query)

        await commit_rollback(session)

    # =========================
    # INVALIDATE OLD TOKENS
    # =========================
    @staticmethod
    async def invalidate_old_tokens(session: AsyncSession, user_id: str):

        query = (
            sql_update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .values(used_flag=True)
            .execution_options(synchronize_session="fetch")
        )

        await session.execute(query)

        await commit_rollback(session)

    