"""
OAuth API Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OAuthProviderBase(BaseModel):
    """OAuth Provider Base Model"""

    name: str = Field(
        ..., max_length=100, description="Provider name (e.g., 'google', 'github')"
    )
    display_name: str = Field(..., max_length=200, description="Display name")
    description: str | None = Field(None, description="Provider description")

    # OAuth Configuration
    client_id: str = Field(..., max_length=500, description="OAuth client ID")
    auth_url: str = Field(..., max_length=1000, description="Authorization URL")
    token_url: str = Field(..., max_length=1000, description="Token URL")
    user_info_url: str = Field(..., max_length=1000, description="User info URL")

    # Configuration Options
    scopes: list[str] = Field(default=[], description="OAuth scopes")
    user_mapping: dict[str, str] = Field(default={}, description="User field mapping")

    # UI Configuration
    icon_url: str | None = Field(None, max_length=500, description="Icon URL")
    button_color: str | None = Field(None, max_length=20, description="Button color")
    sort_order: int = Field(default=0, description="Sort order")
    is_active: bool = Field(default=True, description="Is provider active")


class OAuthProviderCreate(OAuthProviderBase):
    """Create OAuth Provider"""

    client_secret: str = Field(..., max_length=1000, description="OAuth client secret")


class OAuthProviderUpdate(BaseModel):
    """Update OAuth Provider"""

    display_name: str | None = Field(None, max_length=200)
    description: str | None = Field(None)
    client_id: str | None = Field(None, max_length=500)
    client_secret: str | None = Field(None, max_length=1000)
    auth_url: str | None = Field(None, max_length=1000)
    token_url: str | None = Field(None, max_length=1000)
    user_info_url: str | None = Field(None, max_length=1000)
    scopes: list[str] | None = Field(None)
    user_mapping: dict[str, str] | None = Field(None)
    icon_url: str | None = Field(None, max_length=500)
    button_color: str | None = Field(None, max_length=20)
    sort_order: int | None = Field(None)
    is_active: bool | None = Field(None)


class OAuthProviderResponse(BaseModel):
    """OAuth Provider Response"""

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None = None
    client_id: str
    auth_url: str
    token_url: str
    user_info_url: str
    scopes: list[str]
    user_mapping: dict[str, str]
    icon_url: str | None = None
    button_color: str | None = None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OAuthProviderPublic(BaseModel):
    """Public OAuth Provider Info (excluding sensitive info)"""

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None = None
    scopes: list[str]
    icon_url: str | None = None
    button_color: str | None = None
    sort_order: int

    class Config:
        from_attributes = True


class OAuthUserLinkResponse(BaseModel):
    """OAuth User Link Response"""

    id: uuid.UUID
    provider_id: uuid.UUID
    provider_user_id: str
    provider_username: str | None = None
    provider_email: str | None = None
    provider_avatar: str | None = None
    linked_at: datetime
    last_login_at: datetime | None = None

    # Provider Info
    provider: OAuthProviderPublic

    class Config:
        from_attributes = True


class OAuthAuthorizationRequest(BaseModel):
    """OAuth Authorization Request"""

    redirect_uri: str = Field(..., description="Frontend redirect URI")


class OAuthAuthorizationResponse(BaseModel):
    """OAuth Authorization Response"""

    authorization_url: str = Field(..., description="OAuth authorization URL")
    state: str = Field(..., description="CSRF protection state")


class OAuthCallbackResponse(BaseModel):
    """OAuth Callback Response"""

    success: bool
    message: str
    user_id: uuid.UUID | None = None


class OAuthProvidersListResponse(BaseModel):
    """OAuth Providers List Response"""

    list[OAuthProviderPublic]


class OAuthUserLinksResponse(BaseModel):
    """User OAuth Links List Response"""

    links: list[OAuthUserLinkResponse]


class OAuthUnlinkRequest(BaseModel):
    """Unlink OAuth Request"""

    provider_id: uuid.UUID = Field(..., description="Provider ID to unlink")


class OAuthUnlinkResponse(BaseModel):
    """Unlink OAuth Response"""

    success: bool
    message: str
