from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema
from app.service.authentication.users import UserService
from app.dependencies.auth_dependencies import get_jwt_payload_401


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get(
    "/",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def get_user_profile(
    payload: dict = Depends(get_jwt_payload_401),
    session: AsyncSession = Depends(get_db),
):

    result = await UserService.get_user_profile(
        session=session,
        email=payload["email"],
    )

    return ResponseSchema(
        success=True,
        status=200,
        message="Successfully fetched user profile",
        data=result,
    )
   