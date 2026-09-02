from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.auth import LoginSchema
from app.schema.common import (
    ResponseSchema,
    success_response,
)
from app.service.super_admin.auth_service import (
    SuperAdminAuthService,
)
from app.security.rate_limiter import (
    SUPER_ADMIN_LOGIN_RULES,
    get_auth_rate_limiter,
)

router = APIRouter(
    prefix="/super-admin",
    tags=["Super Admin Authentication"],
)


@router.post(
    "/login",
    response_model=ResponseSchema,
)
async def super_admin_login(
    http_request: Request,
    request: LoginSchema,
    session: AsyncSession = Depends(get_db),
):
    await get_auth_rate_limiter().check(
        http_request,
        request,
        SUPER_ADMIN_LOGIN_RULES,
    )

    data = await SuperAdminAuthService.login(
        session=session,
        login=request,
        ip_address=http_request.client.host if http_request.client else None,
    )

    return success_response(
        data=data,
        message="Super Admin login successful.",
    )
