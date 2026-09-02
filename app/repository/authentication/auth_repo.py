from datetime import timedelta
from typing import Optional
from uuid import uuid4
from app.utils.utc import utc_now

from jose import jwt, JWTError

from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.repository.user_session_repo import UserSessionRepository
from app.repository.authentication.users import UsersRepository
from app.config import AsyncSessionLocal
from app.config import JWT_SECRET_KEY, ALGORITHM

SESSION_EXPIRED_DETAIL = "Session expired. Please sign in again."


class JWTRepo:

    def __init__(self, data: dict = None, token: str = None):
        self.data = data or {}
        self.token = token

    def generate_token(self, expires_delta: Optional[timedelta] = None):

        to_encode = self.data.copy()

        expire = utc_now() + (
            expires_delta or timedelta(hours=24)
        )

     
        to_encode.update({
            "exp": expire,
            "jti": str(uuid4()),
        })

        encoded_jwt = jwt.encode(
            to_encode,
            JWT_SECRET_KEY,
            algorithm=ALGORITHM
        )

        return encoded_jwt

    def decode_token(self):

        try:
            decoded_token = jwt.decode(
                self.token,
                JWT_SECRET_KEY,
                algorithms=[ALGORITHM]
            )

            return decoded_token

        except JWTError:
            return None

    @staticmethod
    def extract_token(token: str):

        try:
            return jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[ALGORITHM]
            )

        except JWTError:
            return None


class JWTBearer(HTTPBearer):

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):

        credentials: HTTPAuthorizationCredentials = (
            await super().__call__(request)
        )

        if credentials:

            if credentials.scheme != "Bearer":
                raise HTTPException(
                    status_code=401,
                    detail=SESSION_EXPIRED_DETAIL
                )

            if not await self.verify_jwt(credentials.credentials):
                raise HTTPException(
                    status_code=401,
                    detail=SESSION_EXPIRED_DETAIL
                )

            return credentials.credentials

        raise HTTPException(
            status_code=401,
            detail=SESSION_EXPIRED_DETAIL
        )

    @staticmethod
    async def verify_jwt(jwt_token: str):
        try:
            payload = jwt.decode(
                jwt_token,
                JWT_SECRET_KEY,
                algorithms=[ALGORITHM]
            )

            jti = payload.get("jti")
            user_id = payload.get("user_id")

            if not jti or not user_id:
                return False

            async with AsyncSessionLocal() as session:

                active_session = (
                    await UserSessionRepository.find_active_session_by_jwt_id(
                        session=session,
                        jwt_id=jti
                    )
                )

                if not active_session or str(active_session.user_id) != str(user_id):
                    return False

                user = await UsersRepository.find_by_user_id(
                    session=session,
                    user_id=user_id,
                )

                return bool(
                    user
                    and getattr(user, "deleted_flag", False) is not True
                    and getattr(user, "user_status", None) == "ACTIVE"
                )

        except JWTError:
            return False
