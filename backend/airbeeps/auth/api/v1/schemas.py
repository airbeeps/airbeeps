import uuid

from fastapi_users import schemas
from pydantic import EmailStr


class UserRead(schemas.BaseUser[uuid.UUID]):
    name: str | None = None
    avatar_url: str | None = None
    language: str | None = None


class UserCreate(schemas.CreateUpdateDictModel):
    email: EmailStr | None = None
    password: str
    name: str | None = None
    avatar_url: str | None = None
    language: str | None = "en"  # Default language is English
    is_superuser: bool = False
    is_verified: bool = False
    is_active: bool = True


class UserRegisterRequest(UserCreate):
    """Schema for user registration requests. Extends UserCreate for API endpoint clarity."""


class ChangePasswordRequest(schemas.CreateUpdateDictModel):
    old_password: str
    new_password: str
