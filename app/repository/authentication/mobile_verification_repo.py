from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.mobile_verification import MobileVerification
from app.utils.phone import normalize_phone_number


def _normalise_phone(country_code: str, mobile_number: str) -> tuple[str, str]:
    normalized = normalize_phone_number(country_code, mobile_number)
    return normalized.country_code, normalized.e164


def _phone_match(country_code: str, mobile_number: str):
    normalized = normalize_phone_number(country_code, mobile_number)
    return (
        normalized.country_code,
        normalized.e164,
        normalized.national_number,
    )


class MobileVerificationRepository:

    # ──────────────────────────────────────────
    # CREATE
    # ──────────────────────────────────────────
    @staticmethod
    async def create(
        session: AsyncSession,
        **kwargs,
    ) -> MobileVerification:

        # Normalise phone before storing.
        cc = kwargs.get("country_code", "")
        mn = kwargs.get("mobile_number", "")
        kwargs["country_code"], kwargs["mobile_number"] = _normalise_phone(cc, mn)

        verification = MobileVerification(**kwargs)
        session.add(verification)
        await session.flush()
        return verification

    # ──────────────────────────────────────────
    # FIND (any status)
    # ──────────────────────────────────────────
    @staticmethod
    async def find_by_mobile(
        session: AsyncSession,
        country_code: str,
        mobile_number: str,
    ) -> Optional[MobileVerification]:
        cc, mn, legacy_mn = _phone_match(country_code, mobile_number)
        result = await session.execute(
            select(MobileVerification).where(
                MobileVerification.country_code == cc,
                or_(
                    MobileVerification.mobile_number == mn,
                    MobileVerification.mobile_number == legacy_mn,
                ),
            )
        )
        return result.scalar_one_or_none()

    # ──────────────────────────────────────────
    # GET ACTIVE (not yet verified, not expired)
    # ──────────────────────────────────────────
    @staticmethod
    async def get_active_otp(
        session: AsyncSession,
        country_code: str,
        mobile_number: str,
    ) -> Optional[MobileVerification]:
        cc, mn, legacy_mn = _phone_match(country_code, mobile_number)
        result = await session.execute(
            select(MobileVerification)
            .where(
                MobileVerification.country_code == cc,
                or_(
                    MobileVerification.mobile_number == mn,
                    MobileVerification.mobile_number == legacy_mn,
                ),
                MobileVerification.is_verified.is_(False),
                MobileVerification.expires_at > utc_now_naive(),
            )
            .order_by(MobileVerification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ──────────────────────────────────────────
    # MARK VERIFIED
    # ──────────────────────────────────────────
    @staticmethod
    async def mark_verified(
        session: AsyncSession,
        verification_id: str,
    ) -> None:

        verification = await session.get(MobileVerification, verification_id)
        if verification:
            verification.is_verified = True
            session.add(verification)
            await session.flush()

    # ──────────────────────────────────────────
    # GET VERIFIED (for registration gate)
    # ──────────────────────────────────────────
    @staticmethod
    async def get_verified_mobile(
        session: AsyncSession,
        country_code: str,
        mobile_number: str,
    ) -> Optional[MobileVerification]:
        cc, mn, legacy_mn = _phone_match(country_code, mobile_number)
        result = await session.execute(
            select(MobileVerification).where(
                MobileVerification.country_code == cc,
                or_(
                    MobileVerification.mobile_number == mn,
                    MobileVerification.mobile_number == legacy_mn,
                ),
                MobileVerification.is_verified.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ──────────────────────────────────────────
    # DELETE HELPERS
    # ──────────────────────────────────────────
    @staticmethod
    async def delete_existing_otps(
        session: AsyncSession,
        country_code: str,
        mobile_number: str,
    ) -> None:
        cc, mn, legacy_mn = _phone_match(country_code, mobile_number)
        await session.execute(
            delete(MobileVerification).where(
                MobileVerification.country_code == cc,
                or_(
                    MobileVerification.mobile_number == mn,
                    MobileVerification.mobile_number == legacy_mn,
                ),
            )
        )

    @staticmethod
    async def delete_expired_otps(session: AsyncSession) -> None:
        await session.execute(
            delete(MobileVerification).where(
                MobileVerification.expires_at < utc_now_naive()
            )
        )
