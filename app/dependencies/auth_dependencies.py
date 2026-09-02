import logging
from typing import Any, Dict

from fastapi import HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.repository.authentication.auth_repo import JWTRepo
from app.repository.authentication.users import UsersRepository
from app.repository.user_session_repo import UserSessionRepository


logger = logging.getLogger(__name__)
SESSION_EXPIRED_DETAIL = "Session expired. Please sign in again."


def _session_expired() -> HTTPException:
    return HTTPException(status_code=401, detail=SESSION_EXPIRED_DETAIL)


async def get_jwt_payload_401(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:

    auth = (
        request.headers.get("Authorization")
        or request.headers.get("authorization")
    )

    if not auth:
        logger.warning("Authentication failed: missing Authorization header")
        raise _session_expired()

    parts = auth.strip().split(None, 1)

    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Authentication failed: malformed Authorization header")
        raise _session_expired()

    token = parts[1].strip()

    if not token:
        logger.warning("Authentication failed: empty Bearer token")
        raise _session_expired()

    payload = JWTRepo.extract_token(token)

    if not payload:
        logger.warning("Authentication failed: invalid or expired Bearer token")
        raise _session_expired()

    # =========================
    # SESSION VALIDATION
    # =========================
    jti = payload.get("jti")
    user_id = payload.get("user_id")

    if not jti or not user_id:
        logger.warning("Authentication failed: missing jti/user_id in token")
        raise _session_expired()

    active_session = await UserSessionRepository.find_active_session_by_jwt_id(
        session=session,
        jwt_id=jti,
    )

    if not active_session or str(active_session.user_id) != str(user_id):
        logger.warning(
            "Authentication failed: session terminated for user_id=%s",
            user_id,
        )
        raise _session_expired()

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )
    if (
        not user
        or getattr(user, "deleted_flag", False) is True
        or getattr(user, "user_status", None) != "ACTIVE"
    ):
        logger.warning("Authentication failed: inactive user_id=%s", user_id)
        raise _session_expired()

    logger.debug("Authenticated request for user_id=%s", payload.get("user_id"))
    state = getattr(request, "state", None)
    if state is not None:
        state.jwt_payload = payload
    return payload


async def get_jwt_payload_optional(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any] | None:
    """Same validation as get_jwt_payload_401, but for endpoints that are
    public (viewable while logged out) and only need to know *who* the
    caller is when they happen to be signed in. Returns None instead of
    raising 401 for any missing/invalid/expired token or terminated
    session, so anonymous visitors still get a 200 response.
    """

    auth = (
        request.headers.get("Authorization")
        or request.headers.get("authorization")
    )

    if not auth:
        return None

    parts = auth.strip().split(None, 1)

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()

    if not token:
        return None

    payload = JWTRepo.extract_token(token)

    if not payload:
        return None

    jti = payload.get("jti")
    user_id = payload.get("user_id")

    if not jti or not user_id:
        return None

    active_session = await UserSessionRepository.find_active_session_by_jwt_id(
        session=session,
        jwt_id=jti,
    )

    if not active_session or str(active_session.user_id) != str(user_id):
        return None

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )
    if (
        not user
        or getattr(user, "deleted_flag", False) is True
        or getattr(user, "user_status", None) != "ACTIVE"
    ):
        return None

    logger.debug("Authenticated request for user_id=%s", payload.get("user_id"))
    state = getattr(request, "state", None)
    if state is not None:
        state.jwt_payload = payload
    return payload                                          
