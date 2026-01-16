import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from airbeeps.models import Base  # SQLAlchemy declarative Base

if TYPE_CHECKING:
    from airbeeps.assistants.models import Assistant


class ProviderStatusEnum(enum.Enum):
    """Provider status enumeration"""

    ACTIVE = "ACTIVE"  # Active and available
    INACTIVE = "INACTIVE"  # Disabled
    MAINTENANCE = "MAINTENANCE"  # Under maintenance


class ProviderCategoryEnum(enum.Enum):
    """Provider category enumeration"""

    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"  # OpenAI-compatible endpoints
    PROVIDER_SPECIFIC = "PROVIDER_SPECIFIC"  # Native provider APIs via LiteLLM
    CUSTOM = "CUSTOM"  # User-configured custom endpoints
    LOCAL = "LOCAL"  # Local models (HuggingFace)


class ModelStatusEnum(enum.Enum):
    """Model status enumeration"""

    ACTIVE = "ACTIVE"  # Active and available
    INACTIVE = "INACTIVE"  # Disabled
    UNAVAILABLE = "UNAVAILABLE"  # Temporarily unavailable (e.g., under maintenance)
    DEPRECATED = "DEPRECATED"  # Deprecated


class ModelProvider(Base):
    """Model provider table"""

    __tablename__ = "model_providers"

    # Optional catalog template id (built-in registry); used for UI suggestions
    template_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Provider template id from built-in catalog",
    )

    # Provider name, e.g. OpenAI, Anthropic, Google, etc.
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # Provider display name
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Provider description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider website
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # API base URL
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # API Key
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Provider category - determines routing logic
    category: Mapped[ProviderCategoryEnum] = mapped_column(
        SQLEnum(ProviderCategoryEnum),
        nullable=False,
        default=ProviderCategoryEnum.PROVIDER_SPECIFIC,
        comment="Provider category for routing logic",
    )

    # For CUSTOM category: indicates if endpoint is OpenAI-compatible
    is_openai_compatible: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether custom endpoint follows OpenAI API format",
    )

    # LiteLLM provider name - required for proper routing
    # Examples: "groq", "anthropic", "gemini", "openai", etc.
    litellm_provider: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="LiteLLM provider identifier"
    )

    # Provider status
    status: Mapped[ProviderStatusEnum] = mapped_column(
        SQLEnum(ProviderStatusEnum), default=ProviderStatusEnum.ACTIVE, nullable=False
    )

    # Associated models
    models: Mapped[list["Model"]] = relationship(
        "Model", back_populates="provider", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return self.display_name


class Model(Base):
    """Model table"""

    __tablename__ = "models"

    # Optional catalog template id (built-in registry); used for UI suggestions
    template_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Model template id/name from built-in catalog",
    )

    # Model name (unique identifier within provider)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Model display name
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)

    # Model description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Model supported capabilities list (stored in JSON format)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Provider-specific generation parameters (modalities, image config, tools, etc.)
    generation_config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Provider-specific generation parameters",
    )

    # Model status
    status: Mapped[ModelStatusEnum] = mapped_column(
        SQLEnum(ModelStatusEnum), default=ModelStatusEnum.ACTIVE, nullable=False
    )

    # Maximum context tokens
    max_context_tokens: Mapped[int | None] = mapped_column(nullable=True)

    max_output_tokens: Mapped[int | None] = mapped_column(nullable=True)

    # Provider ID (foreign key)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False
    )

    # Associated provider
    provider: Mapped["ModelProvider"] = relationship(
        "ModelProvider", back_populates="models"
    )

    # Associated assistants - use string forward reference to avoid circular import
    assistants: Mapped[list["Assistant"]] = relationship(
        "Assistant", back_populates="model"
    )

    def __repr__(self):
        return self.display_name


class ModelAssetStatusEnum(enum.Enum):
    """Local model asset status enumeration"""

    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    READY = "READY"
    FAILED = "FAILED"


class ModelAsset(Base):
    """Local model assets (e.g., downloaded Hugging Face snapshots)."""

    __tablename__ = "model_assets"
    __table_args__ = (
        UniqueConstraint(
            "asset_type", "identifier", name="uq_model_assets_asset_type_identifier"
        ),
    )

    # Asset type, e.g. HUGGINGFACE_EMBEDDING
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Identifier within the type, e.g. "BAAI/bge-small-en-v1.5"
    identifier: Mapped[str] = mapped_column(String(500), nullable=False)

    # Optional revision/tag/commit
    revision: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Local path on disk (directory)
    local_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Approx size (bytes)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[ModelAssetStatusEnum] = mapped_column(
        SQLEnum(ModelAssetStatusEnum),
        default=ModelAssetStatusEnum.QUEUED,
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extra metadata (dimensions, normalization, etc.)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
    )
