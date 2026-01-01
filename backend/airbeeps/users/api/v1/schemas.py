import uuid
from datetime import datetime
from decimal import Decimal

from fastapi_users import schemas
from pydantic import BaseModel, EmailStr


class UserRead(schemas.BaseUser[uuid.UUID]):
    email: EmailStr | None = None
    name: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    balance: Decimal | None = None
    total_recharged: Decimal | None = None


class UserUpdate(schemas.CreateUpdateDictModel):
    name: str | None = None
    avatar_url: str | None = None


class UserAdminUpdate(UserUpdate):
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None


class UserProfileUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
