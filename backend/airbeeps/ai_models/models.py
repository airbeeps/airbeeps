import enum
import uuid
from datetime import datetime
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

    # Optional template id from provider registry; used for UI suggestions
    template_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Provider template id from provider registry",
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

    # Optional template id from provider registry; used for UI suggestions
    template_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Model template id/name from provider registry",
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


class ExperimentStatusEnum(enum.Enum):
    """A/B experiment status enumeration"""

    DRAFT = "DRAFT"  # Not yet started
    ACTIVE = "ACTIVE"  # Running
    PAUSED = "PAUSED"  # Temporarily paused
    COMPLETED = "COMPLETED"  # Finished


class ModelExperiment(Base):
    """
    A/B testing experiment for comparing model performance.

    Allows testing different models against each other for quality,
    cost, and latency comparisons.
    """

    __tablename__ = "model_experiments"

    # Experiment name
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[ExperimentStatusEnum] = mapped_column(
        SQLEnum(ExperimentStatusEnum),
        default=ExperimentStatusEnum.DRAFT,
        nullable=False,
    )

    # Variant A model
    model_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Variant B model
    model_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Traffic split (percentage for variant A, B gets the rest)
    traffic_split_percent: Mapped[int] = mapped_column(
        Integer,
        default=50,
        nullable=False,
        comment="Percentage of traffic to variant A (0-100)",
    )

    # Assistant to run the experiment on (optional - applies to all if null)
    assistant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Date range
    start_date: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    end_date: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    # Minimum sample size for statistical significance
    min_sample_size: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    # Experiment configuration
    config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    model_a: Mapped["Model"] = relationship("Model", foreign_keys=[model_a_id])
    model_b: Mapped["Model"] = relationship("Model", foreign_keys=[model_b_id])
    assistant: Mapped["Assistant | None"] = relationship("Assistant")
    assignments: Mapped[list["ExperimentAssignment"]] = relationship(
        "ExperimentAssignment",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ModelExperiment(name='{self.name}', status='{self.status.value}')>"


class ExperimentAssignment(Base):
    """
    Tracks which users are assigned to which variant in an experiment.

    Ensures consistent variant assignment per user/conversation.
    """

    __tablename__ = "experiment_assignments"

    # Experiment
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # User
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Conversation (optional - for per-conversation assignment)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Variant (A or B)
    variant: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        comment="A or B",
    )

    # Assignment timestamp
    assigned_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )

    # Relationships
    experiment: Mapped["ModelExperiment"] = relationship(
        "ModelExperiment", back_populates="assignments"
    )

    # Unique constraint per user+experiment
    __table_args__ = (
        UniqueConstraint(
            "experiment_id", "user_id", name="uq_experiment_user_assignment"
        ),
    )

    def __repr__(self):
        return f"<ExperimentAssignment(experiment_id='{self.experiment_id}', variant='{self.variant}')>"


class ModelUsageMetric(Base):
    """
    Aggregated model usage metrics for analytics.

    Pre-computed daily metrics for dashboard performance.
    """

    __tablename__ = "model_usage_metrics"

    # Model
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Date for daily aggregation
    metric_date: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
    )

    # Usage counts
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Token usage
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Cost
    total_cost_usd: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
    )

    # Latency (aggregated)
    avg_latency_ms: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
    )
    min_latency_ms: Mapped[float] = mapped_column(
        nullable=True,
    )
    max_latency_ms: Mapped[float] = mapped_column(
        nullable=True,
    )
    p95_latency_ms: Mapped[float] = mapped_column(
        nullable=True,
    )

    # Quality metrics (from feedback)
    total_feedback_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    positive_feedback_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    negative_feedback_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Unique users
    unique_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    model: Mapped["Model"] = relationship("Model")

    # Unique constraint per model+date
    __table_args__ = (
        UniqueConstraint("model_id", "metric_date", name="uq_model_usage_metric"),
    )

    def __repr__(self):
        return (
            f"<ModelUsageMetric(model_id='{self.model_id}', date='{self.metric_date}')>"
        )
