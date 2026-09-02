from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.auth_dependencies import (
    get_jwt_payload_401,
)
from app.repository.authentication.users import (
    UsersRepository,
)


def _normalize_role_code(value: str | None) -> str | None:
    if not value:
        return None

    normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    if not normalized.startswith("ROLE_"):
        normalized = f"ROLE_{normalized}"

    return normalized


def _role_codes_from_user(user) -> set[str]:
    role_codes: set[str] = set()

    for role in getattr(user, "roles", []) or []:
        for value in (
            getattr(role, "role_code", None),
            getattr(role, "role_name", None),
        ):
            normalized = _normalize_role_code(value)
            if normalized:
                role_codes.add(normalized)

    return role_codes


async def recruiter_admin_only(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    role_codes = _role_codes_from_user(user)

    allowed_roles = {
        "ROLE_ADMIN",
        "ROLE_RECRUITER",
    }

    if not role_codes.intersection(allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this resource",
        )

    return payload


async def employer_user_only(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    role_codes = _role_codes_from_user(user)

    allowed_roles = {
        "ROLE_ADMIN",
        "ROLE_EMPLOYER",
        "ROLE_RECRUITER",
    }

    if not role_codes.intersection(allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="Only employers can access this resource",
        )

    return payload

async def candidate_only(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    role_codes = _role_codes_from_user(user)

    if "ROLE_CANDIDATE" not in role_codes:
        raise HTTPException(
            status_code=403,
            detail="Only candidates can access this resource",
        )

    return payload

async def super_admin_only(
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    role_codes = _role_codes_from_user(user)

    if "ROLE_SUPER_ADMIN" not in role_codes:
        raise HTTPException(
            status_code=403,
            detail="Only Super Admin can access this resource",
        )

    return payload


async def same_user_or_super_admin(
    user_id,
    payload=Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):
    token_user_id = payload.get("user_id")

    if not token_user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    if str(token_user_id) == str(user_id):
        return payload

    user = await UsersRepository.find_by_user_id(
        session=session,
        user_id=token_user_id,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    if "ROLE_SUPER_ADMIN" in _role_codes_from_user(user):
        return payload

    raise HTTPException(
        status_code=403,
        detail="You can only access your own subscription",
    )
