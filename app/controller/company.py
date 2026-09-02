from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.schema.common import ResponseSchema
from app.repository.authentication.auth_repo import JWTBearer
from app.service.company_service import CompanyService

router = APIRouter(
    prefix="/company",
    tags=["Company"],
    dependencies=[Depends(JWTBearer())]
)


@router.get(
    "/{company_id}",
    response_model=ResponseSchema,
    response_model_exclude_none=True
)
async def get_company_details(
    company_id: str,
    session: AsyncSession = Depends(get_db),
):
    result = await CompanyService.get_company_details(
        session=session,
        company_id=company_id
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    return ResponseSchema(
        success=True,
        status=200,
        message="Successfully fetched company details",
        data=result
    )