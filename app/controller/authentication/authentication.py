from fastapi import APIRouter, Request

from app.schema.common import ResponseSchema, created_response
from app.schema.employer import (
    CandidateRegisterSchema,
    EmployerRegisterSchema,
)
from app.schema.auth import (
    LoginSchema,
    ForgotPasswordSchema,
    ForgotUserIdSchema,
    ResetPasswordSchema,
    ChangePasswordSchema,
    SendMobileOtpSchema,
    VerifyMobileOtpSchema,
)
from app.schema.email_verification import SendOtpSchema, VerifyOtpSchema





from app.service.authentication.auth_service import AuthService
from app.security.rate_limiter import (
    CANDIDATE_REGISTER_RULES,
    CHANGE_PASSWORD_RULES,
    EMPLOYER_REGISTER_RULES,
    FORGOT_PASSWORD_RULES,
    FORGOT_USERID_RULES,
    LOGIN_RULES,
    RESET_PASSWORD_RULES,
    SEND_EMAIL_OTP_RULES,
    SEND_MOBILE_OTP_RULES,
    VERIFY_EMAIL_OTP_RULES,
    VERIFY_MOBILE_OTP_RULES,
    get_auth_rate_limiter,
)

from app.repository.authentication.auth_repo import JWTRepo, JWTBearer
from app.dependencies.auth_dependencies import get_jwt_payload_401



from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials


from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db





router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# Note: individual endpoints can declare JWT dependencies as needed.





# =========================
# EMAIL VERIFICATION OTP
# =========================
@router.post(
    "/send-otp",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def send_otp(
    request: Request,
    request_body: SendOtpSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, SEND_EMAIL_OTP_RULES)
    await AuthService.send_otp_service(session=session, request_body=request_body)
    return ResponseSchema(
        success=True,
        status=200,
        message="otp send to your email.",
        data={},
    )





@router.post(
    "/verify-otp",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def verify_otp(
    request: Request,
    request_body: VerifyOtpSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, VERIFY_EMAIL_OTP_RULES)
    await AuthService.verify_otp_service(session=session, request_body=request_body)
    return ResponseSchema(
        success=True,
        status=200,
        message="Email verified successfully.",
        data={},
    )


# =========================
# MOBILE VERIFICATION OTP
# =========================
@router.post(
    "/send-mobile-otp",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def send_mobile_otp(
    request: Request,
    request_body: SendMobileOtpSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, SEND_MOBILE_OTP_RULES)

    result = await AuthService.send_mobile_otp_service(
        session=session,
        request=request_body,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="OTP sent successfully",
        data=result,
    )


@router.post(
    "/verify-mobile-otp",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
)
async def verify_mobile_otp(
    request: Request,
    request_body: VerifyMobileOtpSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, VERIFY_MOBILE_OTP_RULES)

    result = await AuthService.verify_mobile_otp_service(
        session=session,
        request=request_body,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Mobile number verified successfully",
        data=result,
    )



# =========================
# CANDIDATE REGISTER
# =========================
@router.post(
    "/candidate/register",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
)
async def candidate_register(
    request: Request,
    request_body: CandidateRegisterSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, CANDIDATE_REGISTER_RULES)

    result = await AuthService.candidate_register_service(
        session,
        request_body
    )


    return created_response(
        message="Candidate registered successfully",
        data=result
    )


# =========================
# EMPLOYER REGISTER
# =========================
@router.post(
    "/employer/register",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    status_code=201,
)
async def employer_register(
    request: Request,
    request_body: EmployerRegisterSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, EMPLOYER_REGISTER_RULES)

    result = await AuthService.employer_register_service(
        session,
        request_body
    )


    return created_response(
        message="Employer registered successfully",
        data=result
    )
    


# =========================
# LOGIN
# =========================
@router.post(
    "/login",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def login(
    request: Request,
    request_body: LoginSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, LOGIN_RULES)


    token_data = await AuthService.login_service(
        session,
        request_body
    )

    user = await AuthService.authenticate_user(
        session,
        request_body
    )


    return ResponseSchema(
        success=True,
        status=200,
        message="Login successful",
        data={
            **token_data,
            "user": user
        }
    )

# =========================
# FORGOT PASSWORD
# =========================
@router.post(
    "/forgot-password",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def forgot_password(
    request: Request,
    request_body: ForgotPasswordSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, FORGOT_PASSWORD_RULES)


    result = await AuthService.forgot_password_service(
        session,
        request_body,
    )


    return ResponseSchema(
        success=True,
        status=200,
        message=(
            result["message"]
            if result["message"].startswith("Please enter a registered")
            else "Password reset initiated"
        ),
        data=result
    )
    

# =========================
# FORGOT USER ID
# =========================
@router.post(
    "/forgot-userid",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def forgot_userid(
    request: Request,
    request_body: ForgotUserIdSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, FORGOT_USERID_RULES)

    result = await AuthService.forgot_userid_service(
        session,
        request_body
    )

    return ResponseSchema(
        success=True,
        status=200,
        message=(
            result["message"]
            if result["message"].startswith("Please enter a registered")
            else "User ID retrieval initiated"
        ),
        data=result
    )


# =========================
# RESET PASSWORD
# =========================
@router.post(
    "/reset-password",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def reset_password(
    request: Request,
    request_body: ResetPasswordSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, RESET_PASSWORD_RULES)

    result = await AuthService.reset_password_service(
        session,
        request_body
    )


    return ResponseSchema(
        success=True,
        status=200,
        message="Password reset successful",
        data=result
    )



# =========================
# CHANGE PASSWORD (AUTHENTICATED)
# =========================
@router.post(
    "/change-password",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(get_jwt_payload_401)],
)
async def change_password(
    request: Request,
    request_body: ChangePasswordSchema,
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(request, request_body, CHANGE_PASSWORD_RULES)



    result = await AuthService.change_password_service(
        session=session,
        user_id=str(payload.get("user_id")),
        change_password=request_body,
    )


    return ResponseSchema(
        success=True,
        status=200,
        message="Password changed successfully",
        data=result
    )
   


# =========================
# SIGNOUT
# =========================
@router.post(
    "/signout",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(JWTBearer())],
)
async def signout(
    token: str = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_db),
):
    """
    Sign out the current session.
    Marks the token's session as LOGGED_OUT in the database.
    """

    result = await AuthService.signout_service(
        session=session,
        token=token,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Signed out successfully",
        data=result
    )



# =========================
# SIGNOUT ALL SESSIONS
# =========================
@router.post(
    "/signout-all",
    response_model=ResponseSchema,
    response_model_exclude_none=True,
    dependencies=[Depends(JWTBearer())],
)
async def signout_all(
    token: str = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_db),
):
    """
    Sign out ALL active sessions for the authenticated user.
    Useful when the user suspects a compromised token.
    """
    result = await AuthService.signout_all_service(
        session=session,
        token=token,
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="All sessions signed out successfully",
        data=result
    )
