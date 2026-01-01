import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from airbeeps.ai_models.models import (
    PROVIDER_INTERFACE_TYPES,
    ModelAssetStatusEnum,
    ModelStatusEnum,
    ProviderStatusEnum,
)

# Allowed model capabilities range
ALLOWED_MODEL_CAPABILITIES = [
    "chat",
    "completion",
    "embedding",
    "vision",
    "audio",
    "function_calling",
    "tool_use",
    "code",
    "image_generation",
    "reranker",
    # Extend as needed
]


# Provider Schemas
class ModelProviderBase(BaseModel):
    template_id: str | None = Field(
        None,
        max_length=100,
        description="Optional provider template id from built-in catalog",
    )
    name: str = Field(..., max_length=100, description="Provider name")
    display_name: str = Field(..., max_length=200, description="Provider display name")
    description: str | None = Field(None, description="Provider description")
    website: str | None = Field(None, max_length=500, description="Provider website")
    api_base_url: str = Field(..., max_length=500, description="API base URL")
    interface_type: str = Field(
        PROVIDER_INTERFACE_TYPES["CUSTOM"], description="Interface type"
    )
    litellm_provider: str | None = Field(
        None,
        max_length=100,
        description="LiteLLM custom provider name (e.g., 'groq', 'together_ai', 'mistral'). "
        "Required for OpenAI-compatible providers that need special handling in LiteLLM.",
    )
    status: ProviderStatusEnum = Field(
        ProviderStatusEnum.ACTIVE, description="Provider status"
    )

    @field_validator("interface_type")
    @classmethod
    def validate_interface_type(cls, v):
        if v not in PROVIDER_INTERFACE_TYPES.values():
            allowed_types = list(PROVIDER_INTERFACE_TYPES.values())
            raise ValueError(f"interface_type must be one of: {allowed_types}")
        return v

    @field_validator("template_id", mode="before")
    @classmethod
    def normalize_template_id(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class ModelProviderCreate(ModelProviderBase):
    # Write-only secret: accepted by API, never returned in responses
    api_key: str | None = Field(
        None, max_length=500, description="API key (write-only)"
    )


class ModelProviderUpdate(ModelProviderBase):
    # Write-only secret: accepted by API, never returned in responses
    api_key: str | None = Field(
        None, max_length=500, description="API key (write-only)"
    )


class ModelProviderResponse(ModelProviderBase):
    id: uuid.UUID = Field(..., description="Provider ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# Model Schemas


class ModelBase(BaseModel):
    template_id: str | None = Field(
        None,
        max_length=150,
        description="Optional model template id/name from built-in catalog",
    )
    name: str = Field(..., max_length=200, description="Model name")
    display_name: str = Field(..., max_length=300, description="Model display name")
    description: str | None = Field(None, description="Model description")
    capabilities: list[str] = Field(default=[], description="Model capabilities")
    generation_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific generation parameters (modalities, tools, image config, etc.)",
    )
    status: ModelStatusEnum = Field(ModelStatusEnum.ACTIVE, description="Model status")
    max_context_tokens: int | None = Field(None, description="Maximum context tokens")
    max_output_tokens: int | None = Field(None, description="Maximum output tokens")
    provider_id: uuid.UUID = Field(..., description="Provider ID")

    @field_validator("capabilities", mode="before")
    @classmethod
    def validate_capabilities(cls, v):
        if v is None:
            return []
        invalid = [c for c in v if c not in ALLOWED_MODEL_CAPABILITIES]
        if invalid:
            raise ValueError(
                f"capabilities contains invalid values: {invalid}, allowed range: {ALLOWED_MODEL_CAPABILITIES}"
            )
        return v

    @field_validator("template_id", mode="before")
    @classmethod
    def normalize_template_id(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class ModelCreate(ModelBase):
    pass


class ModelUpdate(BaseModel):
    name: str | None = Field(None, max_length=200, description="Model name")
    display_name: str | None = Field(
        None, max_length=300, description="Model display name"
    )
    description: str | None = Field(None, description="Model description")
    capabilities: list[str] | None = Field(None, description="Model capabilities")
    generation_config: dict[str, Any] | None = Field(
        None, description="Provider-specific generation parameters"
    )
    status: ModelStatusEnum | None = Field(None, description="Model status")
    max_context_tokens: int | None = Field(None, description="Maximum context tokens")
    max_output_tokens: int | None = Field(None, description="Maximum output tokens")
    provider_id: uuid.UUID | None = Field(None, description="Provider ID")

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v):
        if v is None:
            return v
        invalid = [c for c in v if c not in ALLOWED_MODEL_CAPABILITIES]
        if invalid:
            raise ValueError(
                f"capabilities contains invalid values: {invalid}, allowed range: {ALLOWED_MODEL_CAPABILITIES}"
            )
        return v


class ModelResponse(ModelBase):
    id: uuid.UUID = Field(..., description="Model ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    provider: ModelProviderResponse | None = Field(
        None, description="Associated provider"
    )

    class Config:
        from_attributes = True


# ============================================================================
# Catalog (templates) schemas
# ============================================================================


class ProviderTemplateResponse(BaseModel):
    id: str = Field(..., description="Provider template id")
    display_name: str = Field(..., description="Provider template display name")
    description: str | None = Field(None, description="Provider template description")
    website: str | None = Field(None, description="Provider website")
    api_base_url: str = Field(..., description="Default API base URL")
    interface_type: str = Field(..., description="Interface type")
    litellm_provider: str | None = Field(
        None, description="LiteLLM custom provider name (if applicable)"
    )


class ModelTemplateResponse(BaseModel):
    name: str = Field(..., description="Model name / identifier")
    display_name: str = Field(..., description="Model display name")
    description: str | None = Field(None, description="Model description")
    capabilities: list[str] = Field(default=[], description="Model capabilities")
    generation_config: dict[str, Any] = Field(
        default_factory=dict, description="Default provider-specific generation config"
    )
    max_context_tokens: int | None = Field(None, description="Max context tokens")
    max_output_tokens: int | None = Field(None, description="Max output tokens")
    provider_template_id: str | None = Field(
        None, description="Provider template id (when flattened list is returned)"
    )


class ProviderTemplateDetailResponse(ProviderTemplateResponse):
    models: list[ModelTemplateResponse] = Field(default_factory=list)


# ============================================================================
# Local model assets schemas
# ============================================================================


class HuggingFaceDownloadRequest(BaseModel):
    repo_id: str = Field(..., max_length=500, description="Hugging Face repo id")
    revision: str | None = Field(
        None, max_length=200, description="Optional revision/tag/commit"
    )


class HuggingFaceResolveResponse(BaseModel):
    repo_id: str = Field(..., description="Hugging Face repo id")
    revision: str | None = Field(None, description="Revision/tag/commit")
    available: bool = Field(..., description="Whether the model is available locally")
    source: str = Field(
        ...,
        description="Where it was found: model_asset | hf_cache | none",
    )
    local_path: str | None = Field(None, description="Local path when available")
    asset_id: uuid.UUID | None = Field(
        None, description="ModelAsset id when source is model_asset"
    )


class ModelAssetResponse(BaseModel):
    id: uuid.UUID = Field(..., description="Asset ID")
    asset_type: str = Field(..., description="Asset type")
    identifier: str = Field(..., description="Asset identifier")
    revision: str | None = Field(None, description="Revision/tag/commit")
    local_path: str | None = Field(None, description="Local directory path")
    size_bytes: int | None = Field(None, description="Approx size in bytes")
    status: ModelAssetStatusEnum = Field(..., description="Asset status")
    error_message: str | None = Field(None, description="Error message if failed")
    extra_data: dict[str, Any] = Field(
        default_factory=dict, description="Extra metadata"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True
