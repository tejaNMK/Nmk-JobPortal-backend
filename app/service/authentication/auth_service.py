import logging
import secrets
from uuid import uuid4
from datetime import datetime, timedelta

from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from app.service.authentication.sns_service import SNSService

from app.schema.auth import (
    LoginSchema,
    ForgotPasswordSchema,
    ForgotUserIdSchema,
    ResetPasswordSchema,
    ChangePasswordSchema,
)
from app.schema.employer import (
    CandidateRegisterSchema,
    EmployerRegisterSchema,
)

from app.model.authentication.users import Users
from app.model.authentication.user_role import UsersRole
from app.model.authentication.password_history import PasswordHistory
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.company_profile import CompanyProfile
from app.repository.user_session_repo import UserSessionRepository
from app.config import ( AsyncSessionLocal, commit_rollback, MASTER_OTP, MASTER_OTP_ENABLED,)
from app.repository.authentication.mobile_verification_repo import MobileVerificationRepository
from app.model.authentication.mobile_verification import MobileVerification

import sqlalchemy
from app.utils.utc import utc_now_naive
from sqlalchemy import text
from app.repository.authentication.role import RoleRepository
from app.repository.authentication.users import UsersRepository
from app.repository.authentication.user_role import UsersRoleRepository
from app.repository.authentication.auth_repo import JWTRepo
from app.repository.authentication.password_reset_token import PasswordResetTokenRepository
from app.service.authentication.email_service import EmailService
from app.schema.email_verification import SendOtpSchema, VerifyOtpSchema
from app.repository.authentication.email_verification_token import EmailVerificationTokenRepository
from app.service.subscription.user_subscription_service import UserSubscriptionService
from app.service.super_admin.activity_log_service import ActivityLogService
from app.service.notification_service import NotificationService


logger = logging.getLogger(__name__)

# Password Hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# Backward-compatible handle for older unit tests that patch
# app.service.authentication.auth_service.db
db = None


class AuthService:

    # ─────────────────────────────────────────────
    # PASSWORD VALIDATION HELPER
    # ─────────────────────────────────────────────
    @staticmethod
    def _primary_role_from_roles(roles: list[dict]) -> str | None:
        role_codes = {
            str(role.get("role_code") or "").upper()
            for role in roles
        }
        if role_codes.intersection({"ROLE_EMPLOYER", "ROLE_RECRUITER"}):
            return "EMPLOYER"
        if "ROLE_CANDIDATE" in role_codes:
            return "CANDIDATE"
        if role_codes.intersection({"ROLE_ADMIN", "ROLE_SUPER_ADMIN"}):
            return "ADMIN"
        return None

    @staticmethod
    def _passwords_compatible(new_password: str) -> None:
        """Extra safety guard: refuse obvious weak passwords even if schema validation is bypassed."""
        import re
        if new_password is None or not str(new_password).strip():
            raise HTTPException(status_code=400, detail="New Password is required")
        pwd = str(new_password)
        if len(pwd) < 8 or len(pwd) > 25:
            raise HTTPException(status_code=400, detail="Password must be between 8 and 25 characters")
        if " " in pwd:
            raise HTTPException(status_code=400, detail="Password must not contain spaces")
        if not re.search(r"[A-Z]", pwd):
            raise HTTPException(status_code=400, detail="Password must include at least 1 uppercase letter")
        if not re.search(r"[a-z]", pwd):
            raise HTTPException(status_code=400, detail="Password must include at least 1 lowercase letter")
        if not re.search(r"\d", pwd):
            raise HTTPException(status_code=400, detail="Password must include at least 1 number")
        if not re.search(r"[^A-Za-z0-9]", pwd):
            raise HTTPException(status_code=400, detail="Password must include at least 1 special character")

    @staticmethod
    async def _validate_unique_contact(
        session=None,
        email: str | None = None,
        mobile_number: str | None = None,
    ):
        if email:
            existing_email = await UsersRepository.find_by_email(session, email)
            if existing_email:
                raise HTTPException(status_code=400, detail="Email already exists!")

        if mobile_number:
            existing_mobile = await UsersRepository.find_by_mobile(session, mobile_number)
            if existing_mobile:
                raise HTTPException(status_code=400, detail="Mobile number already exists!")
    
    # ─────────────────────────────────────────────
    # DEVELOPMENT MASTER OTP
    # ─────────────────────────────────────────────
    @staticmethod
    def _is_master_otp(otp_code: str) -> bool:
        """
        Returns True only when the development master OTP feature is enabled
        and the supplied OTP matches the configured value.
        """
        if not MASTER_OTP_ENABLED:
            return False

        if not MASTER_OTP:
            return False

        return str(otp_code).strip() == str(MASTER_OTP).strip()

    @staticmethod
    def _verify_otp(
        entered_otp: str,
        hashed_otp: str,
        purpose: str,
    ) -> bool:
        """
        Verify either the actual OTP or the development master OTP.
        """

        if AuthService._is_master_otp(entered_otp):
            logger.warning(
                "Master OTP used",
                extra={
                    "event": "master_otp_used",
                    "otp_purpose": purpose,
                },
            )
            return True

        return pwd_context.verify(entered_otp, hashed_otp)
    # ─────────────────────────────────────────────
    # EMAIL VERIFICATION OTP
    # ─────────────────────────────────────────────
    @staticmethod
    async def send_otp_service(
        session,
        request_body: SendOtpSchema,
    ):
        # Normalize email for consistency (trim + lowercase)
        email = str(request_body.email).strip().lower()

        existing_user = await UsersRepository.find_by_email(session, email)
        if existing_user:
            raise HTTPException(status_code=409, detail="Email is already verified.")

        # Rate limiting: 60-second cooldown between sends.
        last_sent_at = await EmailVerificationTokenRepository.get_last_send_time(session, email=email)
        if last_sent_at:
            seconds_since = (utc_now_naive() - last_sent_at).total_seconds()
            if seconds_since < 60:
                raise HTTPException(
                    status_code=400,
                    detail="OTP resend is limited. Please wait before requesting a new OTP.",
                )

        otp_code = str(secrets.randbelow(900000) + 100000)
        otp_code_hash = pwd_context.hash(otp_code)

        await EmailVerificationTokenRepository.invalidate_active_tokens(session=session, email=email)
        await EmailVerificationTokenRepository.create_token(
            session=session,
            email=email,
            otp_code_hash=otp_code_hash,
            expires_in_minutes=5,
        )

        logger.info(
            "Email verification OTP generated",
            extra={"event": "email_verification_otp_generated"},
        )

        await EmailService.send_email_verification_otp_email(
            to_email=email, otp_code=otp_code, expires_in_minutes=5
        )

        return {"message": "OTP sent successfully"}

    @staticmethod
    async def verify_otp_service(
        session,
        request_body: VerifyOtpSchema,
    ):
        email = str(request_body.email).strip().lower()
        otp_code = str(request_body.otp_code).strip()

        # ---------------------------------------------------------
        # Development Master OTP
        # ---------------------------------------------------------
        if AuthService._is_master_otp(otp_code):

            logger.warning(
                "Master OTP used for email verification",
                extra={"event": "master_otp_used"},
            )

            token_record = await EmailVerificationTokenRepository.find_latest_active_token(
                session=session,
                email=email,
            )

        else:

            token_record = await EmailVerificationTokenRepository.find_valid_otp_record(
                session=session,
                email=email,
                plain_otp_code=otp_code,
            )

        if not token_record:
            raise HTTPException(
                status_code=400,
                detail="Invalid OTP. Please try again.",
            )

        # Mark token used + verified.  Keep the record as proof for pre-registration.
        await EmailVerificationTokenRepository.mark_used_and_verified(
            session, token_id=str(token_record.id)
        )

        # Mark user email as verified (only if the user row already exists).
        user = await UsersRepository.find_by_email(session, email)
        if user:
            await session.execute(
                sqlalchemy.update(Users)
                .where(Users.email == email)
                .values(email_verified=True)
            )
            await commit_rollback(session)

        await ActivityLogService.create_log(
            session=session,
            actor={"user_id": str(user.user_id) if user else None},
            action="EMAIL_VERIFIED",
            entity_type="EmailVerification",
            entity_id=email,
            target_entity_name=email,
            description=f"Email verified for {email}",
        )

        return {"message": "Email verified successfully."}

    # ─────────────────────────────────────────────
    # MOBILE VERIFICATION OTP
    # ─────────────────────────────────────────────
    @staticmethod
    async def send_mobile_otp_service(session, request):
        # phone number must not be blank/None
        if not request.phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        # number must not already be registered
        existing_user = await UsersRepository.find_by_mobile(session, request.phone_number)
        if existing_user:
            raise HTTPException(status_code=400, detail="Mobile number already registered")

        # Purge any previous OTP rows for this mobile (resend idempotency)
        await MobileVerificationRepository.delete_existing_otps(
            session=session,
            country_code=request.country_code,
            mobile_number=request.phone_number,
        )

        otp_code = str(secrets.randbelow(900000) + 100000)
        otp_hash = pwd_context.hash(otp_code)

        await MobileVerificationRepository.create(
            session=session,
            country_code=request.country_code,
            mobile_number=request.phone_number,
            otp_hash=otp_hash,
            expires_at=utc_now_naive() + timedelta(minutes=5),
        )

        # This ensures the OTP exists in DB even if SNS fails.
        # The verify endpoint will find it on a retry.
        await commit_rollback(session)

        # Schemas normalize phone numbers to E.164 before service logic runs.
        mobile_number = request.phone_number

        logger.info(
            "Mobile verification OTP generated",
            extra={"event": "mobile_verification_otp_generated"},
        )

        try:
            response = await SNSService.send_sms(
                mobile_number=mobile_number,
                message=(
                    f"NMK Job Portal OTP: {otp_code}. "
                    f"This OTP is valid for 5 minutes. Do not share this OTP with anyone."
                ),
            )
            logger.info(
                "SNS publish accepted",
                extra={
                    "event": "sns_publish_accepted",
                    "provider_message_id": response.get("MessageId"),
                },
            )
        except Exception as exc:
            # OTP is already committed – user can retry without re-requesting.
            logger.error(
                "SNS publish failed",
                extra={
                    "event": "sns_publish_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
            raise HTTPException(
                status_code=500,
                detail="OTP was generated but could not be delivered. Please try again or contact support.",
            )

        return {"message": "OTP sent successfully"}

    @staticmethod
    async def verify_mobile_otp_service(session, request):
        """
        Verify a mobile OTP and mark it as verified in the DB.

        The verified row is intentionally kept (NOT deleted) so that
        candidate_register_service can confirm verification by calling
        get_verified_mobile().  The row is cleaned up by
        delete_existing_otps() when registration succeeds.
        """
        # Guard: phone number must not be blank/None
        if not request.phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        verification = await MobileVerificationRepository.get_active_otp(
            session=session,
            country_code=request.country_code,
            mobile_number=request.phone_number,
        )

        if not verification:
            raise HTTPException(status_code=400, detail="OTP expired or not found. Please request a new OTP.")

        if not AuthService._verify_otp(
            entered_otp=request.otp_code,
            hashed_otp=verification.otp_hash,
            purpose="Mobile Verification",
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid OTP",
            )

        await MobileVerificationRepository.mark_verified(
            session=session,
            verification_id=verification.verification_id,
        )

        # Commit the is_verified=True update so the next request (registration)
        # sees it in a fresh session.
        await commit_rollback(session)

        logger.info(
            "Mobile verification OTP verified",
            extra={"event": "mobile_verification_otp_verified"},
        )

        await ActivityLogService.create_log(
            session=session,
            actor=None,
            action="MOBILE_VERIFIED",
            entity_type="MobileVerification",
            entity_id=request.phone_number,
            target_entity_name=request.phone_number,
            description=f"Mobile number verified for {request.phone_number}",
        )

        return {"message": "Mobile number verified successfully"}

    # ─────────────────────────────────────────────
    # CANDIDATE REGISTER
    # ─────────────────────────────────────────────
    @staticmethod
    async def candidate_register_service(
        session,
        register: CandidateRegisterSchema | None = None,
    ):
        if register is None:
            register = session
            session = None

        try:
            # ── Validate email uniqueness ──
            phone_number = (register.phone_number or "").strip()
            await AuthService._validate_unique_contact(
                session=session,
                email=register.email,
                mobile_number=phone_number,
            )

            if session is not None:
                # ── Email verification gate ──
                verified_token = await EmailVerificationTokenRepository.find_recently_verified_token(
                    session,
                    email=str(register.email).strip().lower(),
                )
                if not verified_token:
                    raise HTTPException(
                        status_code=400,
                        detail="Please verify your email before registration.",
                    )

                # ── Mobile verification gate ──
                # FIX: phone_number is Optional in CandidateRegisterSchema.
                # If the client omits it (None or empty string), skip the check
                # and raise a clear 400 instead of letting get_verified_mobile
                # return None and silently blocking registration.
                if not phone_number:
                    raise HTTPException(
                        status_code=400,
                        detail="Phone number is required for registration.",
                    )

                verification = await MobileVerificationRepository.get_verified_mobile(
                    session=session,
                    country_code=register.country_code,
                    mobile_number=phone_number,
                )

                if not verification:
                    raise HTTPException(
                        status_code=400,
                        detail="Please verify your mobile number before registration.",
                    )

            # ── Password validation ──
            if register.password != register.confirm_password:
                raise HTTPException(status_code=400, detail="Passwords do not match")
            AuthService._passwords_compatible(register.password)

            # ── Role existence check ──
            role = await RoleRepository.find_by_role_code(session, "ROLE_CANDIDATE")
            if not role:
                raise HTTPException(status_code=500, detail="Candidate role is not configured!")

            # ── Create user ──
            user_payload = {
                "first_name": register.first_name,
                "middle_name": getattr(register, "middle_name", None),
                "last_name": register.last_name,
                "email": register.email,
                "mobile_number": phone_number,
                "country_code": register.country_code,
                "password_hash": pwd_context.hash(register.password),
                "user_status": "ACTIVE",
                "mobile_verified": True,
            }

            created_user = await UsersRepository.create(session=session, **user_payload)

            if session is not None:
                # Mark email verified on the new user row
                await session.execute(
                    sqlalchemy.update(Users)
                    .where(Users.user_id == created_user.user_id)
                    .values(email_verified=True)
                )

                # Clean up OTP proofs now that registration is done
                await EmailVerificationTokenRepository.delete_tokens_by_email(
                    session=session,
                    email=str(register.email).strip().lower(),
                )
                await MobileVerificationRepository.delete_existing_otps(
                    session=session,
                    country_code=register.country_code,
                    mobile_number=phone_number,
                )

            # ── Assign role ──
            await UsersRoleRepository.create(
                session=session,
                user_id=created_user.user_id,
                role_id=role.role_id,
                assigned_at=utc_now_naive(),
            )

            if session is not None:
                await UserSubscriptionService.assign_default_subscription(
                    session=session,
                    user_id=created_user.user_id,
                    role="CANDIDATE",
                    remarks="Assigned during candidate registration.",
                )

            # ── Create candidate profile shell ──
            if session is not None:
                candidate_profile = CandidateProfile(
                    user_id=created_user.user_id,
                    created_by=str(created_user.user_id),
                    updated_by=str(created_user.user_id),
                )
                session.add(candidate_profile)
                await commit_rollback(session)

            if session is not None:
                await ActivityLogService.create_log(
                    session=session,
                    actor={
                        "user_id": str(created_user.user_id),
                        "role_code": "ROLE_CANDIDATE",
                    },
                    action="REGISTRATION",
                    entity_type="Candidate",
                    entity_id=str(created_user.user_id),
                    target_entity_name=(
                        f"{created_user.first_name or ''} "
                        f"{created_user.last_name or ''}"
                    ).strip() or created_user.email,
                    description="Candidate registered",
                )
                await ActivityLogService.create_log(
                    session=session,
                    actor={
                        "user_id": str(created_user.user_id),
                        "role_code": "ROLE_CANDIDATE",
                    },
                    action="PROFILE_CREATED",
                    entity_type="CandidateProfile",
                    entity_id=str(candidate_profile.candidate_id),
                    target_entity_name=(
                        f"{created_user.first_name or ''} "
                        f"{created_user.last_name or ''}"
                    ).strip() or created_user.email,
                    description="Candidate profile created",
                )
                await NotificationService.create_for_super_admins(
                    session,
                    notification_type="CANDIDATE_REGISTERED",
                    title="New candidate registered",
                    message=f"{created_user.first_name} {created_user.last_name or ''} registered as a candidate.".strip(),
                    entity_type="user",
                    entity_id=str(created_user.user_id),
                    target_route=f"/super-admin/candidates/{created_user.user_id}",
                    event_key=f"candidate_registered:{created_user.user_id}",
                    commit=True,
                )

            return {
                "message": "Candidate registered successfully",
                "desired_role": register.desired_role,
                "role_code": "ROLE_CANDIDATE",
            }

        except HTTPException:
            if session is not None:
                await session.rollback()
            raise
        except IntegrityError as exc:
            if session is not None:
                await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            if session is not None:
                await session.rollback()
            logger.exception("Unexpected error during candidate registration")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during registration",
            ) from exc

    # ─────────────────────────────────────────────
    # EMPLOYER REGISTER
    # ─────────────────────────────────────────────
    @staticmethod
    async def employer_register_service(session, register: EmployerRegisterSchema):
        try:
            phone_number = (register.phone_number or "").strip()
            # ── Validate uniqueness ──
            await AuthService._validate_unique_contact(
                session=session,
                email=register.work_email,
                mobile_number=phone_number,
            )

            if session is not None:
                # ── Email verification gate ──
                verified_token = await EmailVerificationTokenRepository.find_recently_verified_token(
                    session,
                    email=str(register.work_email).strip().lower(),
                )
                if not verified_token:
                    raise HTTPException(
                        status_code=400,
                        detail="Please verify your email before registration.",
                    )

                # ── Mobile verification gate ──
                if not phone_number:
                    raise HTTPException(
                        status_code=400,
                        detail="Phone number is required for registration.",
                    )

                verification = await MobileVerificationRepository.get_verified_mobile(
                    session=session,
                    country_code=register.country_code,
                    mobile_number=phone_number,
                )
                if not verification:
                    raise HTTPException(
                        status_code=400,
                        detail="Please verify your mobile number before registration.",
                    )

            # ── Password validation ──
            if register.password != register.confirm_password:
                raise HTTPException(status_code=400, detail="Passwords do not match")
            AuthService._passwords_compatible(register.password)

            # ── Role existence check ──
            role = await RoleRepository.find_by_role_code(session, "ROLE_RECRUITER")
            if not role:
                raise HTTPException(status_code=500, detail="Recruiter role is not configured!")

            # ── Create user ──
            user_payload = {
                "first_name": register.first_name,
                "middle_name": getattr(register, "middle_name", None),
                "last_name": register.last_name,
                "email": register.work_email,
                "mobile_number": phone_number,
                "country_code": register.country_code,
                "password_hash": pwd_context.hash(register.password),
                "user_status": "ACTIVE",
                "mobile_verified": True,
            }

            created_user = await UsersRepository.create(session=session, **user_payload)

            if session is not None:
                await session.execute(
                    sqlalchemy.update(Users)
                    .where(Users.user_id == created_user.user_id)
                    .values(email_verified=True)
                )
                await EmailVerificationTokenRepository.delete_tokens_by_email(
                    session=session,
                    email=str(register.work_email).strip().lower(),
                )
                await MobileVerificationRepository.delete_existing_otps(
                    session=session,
                    country_code=register.country_code,
                    mobile_number=phone_number,
                )

            # ── Assign role ──
            await UsersRoleRepository.create(
                session=session,
                user_id=created_user.user_id,
                role_id=role.role_id,
                assigned_at=utc_now_naive(),
            )

            if session is not None:
                await UserSubscriptionService.assign_default_subscription(
                    session=session,
                    user_id=created_user.user_id,
                    role="EMPLOYER",
                    remarks="Assigned during employer registration.",
                )

            # ── Employer profile ──
            employer_profile = EmployerProfile(
                id=str(uuid4()),
                user_id=created_user.user_id,
                company_name=register.company_name,
                company_email=register.work_email,
                company_mobile=phone_number,
                created_by=str(created_user.user_id),
                updated_by=str(created_user.user_id),
            )
            session.add(employer_profile)
            await session.flush()

            # ── Company profile ──
            result = await session.execute(text("SELECT COUNT(*) FROM company_profiles"))
            count = result.scalar() + 1

            company_profile = CompanyProfile(
                company_id=f"COMP{count:03d}",
                employer_id=employer_profile.id,
                company_name=register.company_name,
                website=register.website,
                description=f"{register.company_name} company profile",
                industry="IT",
                size=register.team_size,
                location=None,
            )
            session.add(company_profile)
            await commit_rollback(session)

            await ActivityLogService.create_log(
                session=session,
                actor={
                    "user_id": str(created_user.user_id),
                    "role_code": "ROLE_EMPLOYER",
                },
                action="REGISTRATION",
                entity_type="Employer",
                entity_id=str(created_user.user_id),
                target_entity_name=register.company_name,
                description="Employer registered",
                metadata={"company_id": company_profile.company_id},
            )
            await NotificationService.create_for_super_admins(
                session,
                notification_type="RECRUITER_REGISTERED",
                title="New recruiter registered",
                message=f"{register.company_name} registered a recruiter account.",
                entity_type="user",
                entity_id=str(created_user.user_id),
                target_route=f"/super-admin/employers/{created_user.user_id}",
                metadata={"company_id": company_profile.company_id},
                event_key=f"recruiter_registered:{created_user.user_id}",
                commit=True,
            )
            await NotificationService.create_for_super_admins(
                session,
                notification_type="COMPANY_APPROVAL_PENDING",
                title="Company approval pending",
                message=f"{register.company_name} requested company approval.",
                entity_type="company",
                entity_id=company_profile.company_id,
                target_route=f"/super-admin/company-approvals?company_id={company_profile.company_id}",
                event_key=f"company_approval_pending:{company_profile.company_id}",
                commit=True,
            )

            return {"message": "Employer registered successfully"}

        except HTTPException:
            if session is not None:
                await session.rollback()
            raise
        except IntegrityError as exc:
            if session is not None:
                await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            if session is not None:
                await session.rollback()
            logger.exception("Unexpected error during employer registration")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during registration",
            ) from exc

    # ─────────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────────
    @staticmethod
    async def login_service(
        session,
        login: LoginSchema | None = None,
        log_activity: bool = True,
    ):
        if login is None:
            login = session
            session = None

        email = str(login.email).strip().lower()
        user = await UsersRepository.find_by_email(session, email)

        if not user:
            raise HTTPException(status_code=404, detail="User not found!")

        if getattr(user, "deleted_flag", False) is True:
            raise HTTPException(status_code=404, detail="User not found!")

        if not pwd_context.verify(login.password, user.password_hash):
            raise HTTPException(status_code=400, detail="Invalid password!")

        token = JWTRepo(data={"user_id": str(user.user_id), "email": user.email}).generate_token()

        payload = JWTRepo.extract_token(token)
        if payload and session:
            await UserSessionRepository.create_session(
                session=session,
                user_id=str(user.user_id),
                jwt_id=payload.get("jti", ""),
                login_method="EMAIL",
            )

        if session and log_activity:
            await ActivityLogService.create_log(
                session=session,
                actor=user,
                action="LOGIN",
                entity_type="User",
                entity_id=str(user.user_id),
                target_entity_name=(
                    f"{user.first_name or ''} {user.last_name or ''}"
                ).strip() or user.email,
                description="User logged in",
            )

        return {"access_token": token, "token_type": "bearer"}

    # ─────────────────────────────────────────────
    # AUTHENTICATE USER
    # ─────────────────────────────────────────────
    @staticmethod
    async def authenticate_user(session, login: LoginSchema):
        email = str(login.email).strip().lower()
        user = await UsersRepository.find_by_email(session, email)

        if not user:
            raise HTTPException(status_code=404, detail="User not found!")

        roles = []
        try:
            if hasattr(user, "roles") and user.roles:
                roles = [
                    {"role_name": role.role_name, "role_code": role.role_code}
                    for role in user.roles
                ]
        except Exception:
            logger.warning("Role mapping failed during authenticate_user")
            roles = []

        role = AuthService._primary_role_from_roles(roles)
        summary = await UserSubscriptionService.get_current_subscription_summary(
            session=session,
            user_id=user.user_id,
            expected_type=role,
        )
        plan_name = summary.subscription_name if summary else "No Active Plan"

        return {
            "user_id": str(user.user_id),
            "email": user.email,
            "status": user.user_status,
            "role": role,
            "roles": roles,
            "subscription": summary.model_dump(mode="json") if summary else None,
            "subscription_name": plan_name,
            "plan_name": plan_name,
        }

    # ─────────────────────────────────────────────
    # FORGOT PASSWORD
    # ─────────────────────────────────────────────
    @staticmethod
    async def forgot_password_service(
        session=None,
        forgot_password: ForgotPasswordSchema | None = None,
    ):
        if forgot_password is None:
            forgot_password = session
            session = None

        if forgot_password.email:
            email = str(forgot_password.email).strip().lower()
            user = await UsersRepository.find_by_email(session, email)
        elif forgot_password.mobile_number:
            user = await UsersRepository.find_by_mobile(session, forgot_password.mobile_number)
        else:
            user = None

        if not user:
            if forgot_password.email:
                return {"message": "Please enter a registered email address."}
            return {"message": "Please enter a registered mobile number."}

        otp_code = str(secrets.randbelow(900000) + 100000)
        otp_code_hash = pwd_context.hash(otp_code)

        await PasswordResetTokenRepository.invalidate_old_tokens(session=session, user_id=str(user.user_id))
        await PasswordResetTokenRepository.create_reset_token(
            session=session,
            user_id=str(user.user_id),
            otp_code_hash=otp_code_hash,
            expires_in_minutes=60,
        )

        logger.info(
            "Password reset OTP generated",
            extra={"event": "password_reset_otp_generated"},
        )

        try:
            if forgot_password.email:
                await EmailService.send_password_reset_otp_email(
                    to_email=user.email,
                    otp_code=otp_code,
                    expires_in_minutes=60,
                )
            else:
                mobile_number = user.mobile_number
                if mobile_number and not str(mobile_number).startswith("+"):
                    mobile_number = f"{user.country_code}{mobile_number}"
                await SNSService.send_sms(
                    mobile_number=mobile_number,
                    message=(
                        f"NMK Job Portal Password Reset OTP: {otp_code}. "
                        f"This OTP is valid for 60 minutes. Do not share this OTP."
                    ),
                )
        except Exception as exc:
            logger.exception("Forgot password delivery failed")
            raise HTTPException(status_code=500, detail=str(exc))

        return {"message": "Password reset initiated", "expires_in_minutes": 60}

    # ─────────────────────────────────────────────
    # FORGOT USER ID
    # ─────────────────────────────────────────────
    @staticmethod
    async def forgot_userid_service(
        session=None,
        forgot_userid: ForgotUserIdSchema | None = None,
    ):
        if forgot_userid is None:
            forgot_userid = session
            session = None

        user = None
        if forgot_userid.email:
            email = str(forgot_userid.email).strip().lower()
            user = await UsersRepository.find_by_email(session, email)
        elif forgot_userid.mobile_number:
            user = await UsersRepository.find_by_mobile(session, forgot_userid.mobile_number)

        if not user:
            return {
                "message": (
                    "If an account exists with the provided information, "
                    "the login email has been sent to the registered mobile number."
                )
            }

        if user and user.mobile_number:
            try:
                mobile_number = user.mobile_number
                if mobile_number and not str(mobile_number).startswith("+"):
                    mobile_number = f"{user.country_code}{mobile_number}"
                await SNSService.send_sms(
                    mobile_number=mobile_number,
                    message=f"NMK Job Portal Login UserID: {user.email}",
                )
            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail="We're unable to process your request right now. Please try again later.",
                )

        return {
            "message": (
                "If an account exists with the provided information, "
                "the login email has been sent to the registered mobile number."
            )
        }

    # ─────────────────────────────────────────────
    # RESET PASSWORD
    # ─────────────────────────────────────────────
    @staticmethod
    async def reset_password_service(
        session=None,
        reset_password: ResetPasswordSchema | None = None,
    ):
        if reset_password is None:
            reset_password = session
            session = None

        if reset_password.email:
            email = str(reset_password.email).strip().lower()
            user = await UsersRepository.find_by_email(session, email)
        else:
            user = await UsersRepository.find_by_mobile(session, reset_password.mobile_number)

        if not user:
            raise HTTPException(status_code=404, detail="User not found!")

        # ---------------------------------------------------------
        # Development Master OTP
        # ---------------------------------------------------------
        if AuthService._is_master_otp(reset_password.otp_code):

            logger.warning(
                "Master OTP used for password reset",
                extra={"event": "master_otp_used", "otp_purpose": "password_reset"},
            )

            token_record = await PasswordResetTokenRepository.find_latest_active_token(
                session=session,
                user_id=str(user.user_id),
            )

        else:

            token_record = await PasswordResetTokenRepository.find_valid_otp_by_user_and_code(
                session=session,
                user_id=str(user.user_id),
                plain_otp_code=reset_password.otp_code,
            )

        if not token_record:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired OTP code!",
            )

        user = await UsersRepository.find_by_user_id(session, str(token_record.user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found!")

        if pwd_context.verify(reset_password.new_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail="New password cannot be the same as the current password",
            )

        new_password_hash = pwd_context.hash(reset_password.new_password)
        await UsersRepository.update_password(session=session, email=user.email, password_hash=new_password_hash)
        await PasswordResetTokenRepository.mark_token_as_used(session=session, token_id=str(token_record.token_id))
        await ActivityLogService.create_log(
            session=session,
            actor=user,
            action="PASSWORD_RESET",
            entity_type="User",
            entity_id=str(user.user_id),
            target_entity_name=(f"{user.first_name or ''} {user.last_name or ''}").strip() or user.email,
            description="Password reset completed",
        )

        return {"message": "Password has been reset successfully"}

    # ─────────────────────────────────────────────
    # CHANGE PASSWORD (AUTHENTICATED)
    # ─────────────────────────────────────────────
    @staticmethod
    async def change_password_service(
        session=None,
        user_id: str | None = None,
        change_password: ChangePasswordSchema | None = None,
    ):
        if change_password is None or not isinstance(change_password, ChangePasswordSchema):
            raise HTTPException(status_code=400, detail="Invalid request payload for password change")

        if not user_id:
            raise HTTPException(status_code=400, detail="User id is required")

        user = await UsersRepository.find_by_user_id(session, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found!")

        if not pwd_context.verify(change_password.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Invalid current password")

        if pwd_context.verify(change_password.new_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail="New password cannot be the same as the current password",
            )

        AuthService._passwords_compatible(change_password.new_password)
        new_password_hash = pwd_context.hash(change_password.new_password)
        await UsersRepository.update_password(session=session, email=user.email, password_hash=new_password_hash)
        await ActivityLogService.create_log(
            session=session,
            actor=user,
            action="PASSWORD_CHANGED",
            entity_type="User",
            entity_id=str(user.user_id),
            target_entity_name=(f"{user.first_name or ''} {user.last_name or ''}").strip() or user.email,
            description="Password changed by user",
        )

        if change_password.sign_out_everywhere:
            count = await UserSessionRepository.logout_all_sessions(
                session=session,
                user_id=str(user.user_id),
            )
            await ActivityLogService.create_log_for_user_id(
                session=session,
                user_id=str(user.user_id),
                action="LOGOUT_ALL",
                entity_type="UserSession",
                entity_id=str(user.user_id),
                description=f"User logged out all sessions after password change: {count}",
                metadata={
                    "sessions_terminated": count,
                    "reason": "PASSWORD_CHANGED",
                },
            )
            return {
                "message": "Password changed successfully",
                "sessions_terminated": count,
            }

        return {"message": "Password changed successfully"}

    # ─────────────────────────────────────────────
    # SIGNOUT
    # ─────────────────────────────────────────────
    @staticmethod
    async def signout_service(session, token: str) -> dict:
        payload = JWTRepo.extract_token(token)
        if not payload:
            raise HTTPException(status_code=403, detail="Invalid or expired token")

        jti = payload.get("jti")
        if not jti:
            return {"message": "Signed out successfully"}

        await UserSessionRepository.logout_session(session=session, jwt_id=jti)
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=payload.get("user_id"),
            action="LOGOUT",
            entity_type="UserSession",
            entity_id=jti,
            description="User logged out",
        )
        return {"message": "Signed out successfully"}

    @staticmethod
    async def signout_all_service(session, token: str) -> dict:
        payload = JWTRepo.extract_token(token)
        if not payload:
            raise HTTPException(status_code=403, detail="Invalid or expired token")

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=403, detail="Invalid token payload")

        count = await UserSessionRepository.logout_all_sessions(session=session, user_id=user_id)
        await ActivityLogService.create_log_for_user_id(
            session=session,
            user_id=user_id,
            action="LOGOUT_ALL",
            entity_type="UserSession",
            entity_id=user_id,
            description=f"User logged out all sessions: {count}",
            metadata={"sessions_terminated": count},
        )
        return {"message": "All sessions signed out successfully", "sessions_terminated": count}

    # ─────────────────────────────────────────────
    # GENERATE DEFAULT ROLES
    # ─────────────────────────────────────────────
    async def generate_role(session):
        default_roles = [
    {
        "role_name": "Super Admin",
        "role_code": "ROLE_SUPER_ADMIN",
    },
    {
        "role_name": "Admin",
        "role_code": "ROLE_ADMIN",
    },
    {
        "role_name": "Recruiter",
        "role_code": "ROLE_RECRUITER",
    },
    {
        "role_name": "Candidate",
        "role_code": "ROLE_CANDIDATE",
    },
]

        roles = await RoleRepository.find_by_role_codes(
            session, [role["role_code"] for role in default_roles]
        )
        existing_role_codes = {role.role_code for role in roles}
        missing_roles = [r for r in default_roles if r["role_code"] not in existing_role_codes]

        if missing_roles:
            await RoleRepository.create_list(session, missing_roles)


generate_role = AuthService.generate_role
