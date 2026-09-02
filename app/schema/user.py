from typing import Optional, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class RoleSchema(BaseModel):
    role_id: UUID
    role_name: str
    role_code: str

    model_config = ConfigDict(from_attributes=True)


class UserResponseSchema(BaseModel):
    user_id: UUID
    first_name: str
    last_name: Optional[str]
    email: Optional[EmailStr]
    mobile_number: Optional[str]
    user_status: str
    email_verified: bool
    mobile_verified: bool

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    roles: Optional[List[RoleSchema]] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
