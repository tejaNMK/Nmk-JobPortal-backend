from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.schema.common import ResponseSchema, success_response
from app.schema.super_admin.settings import SystemSettingsUpdateRequest
from app.service.super_admin.settings_service import SystemSettingsService

router = APIRouter(
    prefix="/super-admin/settings",
    tags=["Super Admin Settings"],
    dependencies=[Depends(super_admin_only)],
)


@router.get("", response_model=ResponseSchema)
async def get_settings(
    session: AsyncSession = Depends(get_db),
):
    data = await SystemSettingsService.get_settings(session=session)
    return success_response(
        data=data.model_dump(),
        message="System settings fetched successfully.",
    )


@router.patch("", response_model=ResponseSchema)
async def update_settings(
    request: SystemSettingsUpdateRequest,
    payload=Depends(super_admin_only),
    session: AsyncSession = Depends(get_db),
):
    data = await SystemSettingsService.update_settings(
        session=session,
        request=request,
        actor=payload,
    )
    return success_response(
        data=data.model_dump(),
        message="System settings updated successfully.",
    )
