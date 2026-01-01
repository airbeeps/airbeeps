import json
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConfigCreate(BaseModel):
    """Request model for creating configuration items"""

    key: str = Field(
        ..., min_length=1, max_length=255, description="Configuration key name"
    )
    value: Any = Field(..., description="Configuration value")
    description: str | None = Field(None, description="Configuration description")
    is_public: bool = Field(False, description="Whether this is a public configuration")
    is_enabled: bool = Field(
        True, description="Whether this configuration item is enabled"
    )


class ConfigUpdate(BaseModel):
    """Request model for updating configuration items"""

    value: Any | None = Field(None, description="Configuration value")
    description: str | None = Field(None, description="Configuration description")
    is_public: bool | None = Field(
        None, description="Whether this is a public configuration"
    )
    is_enabled: bool | None = Field(
        None, description="Whether this configuration item is enabled"
    )


class ConfigResponse(BaseModel):
    """Configuration item response model"""

    id: uuid.UUID
    key: str
    value: Any
    description: str | None
    is_public: bool
    is_enabled: bool
    created_at: Any
    updated_at: Any

    @field_validator("value", mode="before")
    @classmethod
    def parse_json_value(cls, v: Any) -> Any:
        """Parse JSON string value to Python object."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    class Config:
        from_attributes = True


class PublicConfigResponse(BaseModel):
    """Public configuration response model"""

    key: str
    value: Any

    class Config:
        from_attributes = True


class ConfigListResponse(BaseModel):
    """Configuration list response model"""

    configs: list[ConfigResponse]
    total: int


class PublicConfigsResponse(BaseModel):
    """Public configurations collection response model"""

    configs: dict[str, Any] = Field(..., description="Configuration key-value pairs")


class ConfigBatchUpdate(BaseModel):
    """Request model for batch updating configurations"""

    configs: dict[str, Any] = Field(
        ..., description="Configuration key-value pairs to update"
    )
