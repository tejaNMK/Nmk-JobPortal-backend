from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.schema.common import ResponseSchema, created_response, success_response
from app.schema.profile import (
    CompanyProfileCreate,
    CompanyProfileUpdate,
    EmployerProfileCreate,
    EmployerProfileUpdate,
)
from app.service.profile_service import CompanyProfileService, EmployerProfileService


company_profile_router = APIRouter(
    prefix="/company-profile",
    tags=["Company Profile"],
)

employer_profile_router = APIRouter(
    prefix="/employer-profile",
    tags=["Employer Profile"],
)

companies_router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


@company_profile_router.post("", response_model=ResponseSchema, status_code=201)
async def create_company_profile(
    request: CompanyProfileCreate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.create(session, payload, request)
    return created_response(
        data=data.model_dump(),
        message="Company profile created successfully.",
    )


@company_profile_router.get("", response_model=ResponseSchema)
async def get_company_profile(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.get(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Company profile fetched successfully.",
    )


@company_profile_router.patch("", response_model=ResponseSchema)
async def update_company_profile(
    request: CompanyProfileUpdate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.update(session, payload, request)
    return success_response(
        data=data.model_dump(),
        message="Company profile updated successfully.",
    )


@company_profile_router.put("", response_model=ResponseSchema)
async def put_company_profile(
    request: CompanyProfileUpdate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.update(session, payload, request)
    return success_response(
        data=data.model_dump(),
        message="Company profile updated successfully.",
    )


@company_profile_router.post("/logo", response_model=ResponseSchema)
async def upload_company_logo(
    logo: UploadFile = File(...),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.upload_logo(session, payload, logo)
    return success_response(
        data=data.model_dump(),
        message="Company logo uploaded successfully.",
    )


@company_profile_router.delete("/logo", response_model=ResponseSchema)
async def delete_company_logo(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.delete_logo(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Company logo deleted successfully.",
    )


@employer_profile_router.post("", response_model=ResponseSchema, status_code=201)
async def create_employer_profile(
    request: EmployerProfileCreate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.create(session, payload, request)
    return created_response(
        data=data.model_dump(),
        message="Employer profile created successfully.",
    )


@employer_profile_router.get("", response_model=ResponseSchema)
async def get_employer_profile(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.get(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Employer profile fetched successfully.",
    )


@employer_profile_router.patch("", response_model=ResponseSchema)
async def update_employer_profile(
    request: EmployerProfileUpdate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.update(session, payload, request)
    return success_response(
        data=data.model_dump(),
        message="Employer profile updated successfully.",
    )


@employer_profile_router.put("", response_model=ResponseSchema)
async def put_employer_profile(
    request: EmployerProfileUpdate,
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.update(session, payload, request)
    return success_response(
        data=data.model_dump(),
        message="Employer profile updated successfully.",
    )


@employer_profile_router.post("/photo", response_model=ResponseSchema)
async def upload_profile_photo(
    photo: UploadFile = File(...),
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.upload_photo(session, payload, photo)
    return success_response(
        data=data.model_dump(),
        message="Profile photo uploaded successfully.",
    )


@employer_profile_router.delete("/photo", response_model=ResponseSchema)
async def delete_profile_photo(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.delete_photo(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Profile photo deleted successfully.",
    )


@employer_profile_router.get("/completion", response_model=ResponseSchema)
async def get_profile_completion(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.completion(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Employer profile completion fetched successfully.",
    )


@employer_profile_router.get("/dashboard", response_model=ResponseSchema)
async def get_employer_profile_dashboard(
    payload: dict = Depends(employer_user_only),
    session: AsyncSession = Depends(get_db),
):
    data = await EmployerProfileService.dashboard(session, payload)
    return success_response(
        data=data.model_dump(),
        message="Employer profile dashboard fetched successfully.",
    )


@companies_router.get("", response_model=ResponseSchema)
async def search_companies(
    name: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    company_size: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    verification_status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="company_name"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.search(
        session=session,
        name=name,
        industry=industry,
        company_size=company_size,
        location=location,
        verification_status=verification_status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return success_response(
        data=data.model_dump(),
        message="Companies fetched successfully.",
    )


@companies_router.get("/{company_id}", response_model=ResponseSchema)
async def get_public_company_profile(
    company_id: str,
    session: AsyncSession = Depends(get_db),
):
    data = await CompanyProfileService.public_get(session, company_id)
    return success_response(
        data=data.model_dump(),
        message="Company profile fetched successfully.",
    )
