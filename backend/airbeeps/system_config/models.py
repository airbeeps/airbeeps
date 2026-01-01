import json
from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from airbeeps.models import Base


class SystemConfig(Base):
    """System configuration table"""

    __tablename__ = "system_configs"

    # Configuration key name, unique
    key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Configuration key name",
    )

    # Configuration value stored in JSON format, supports various data types
    value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Configuration value (JSON format)"
    )

    # Configuration description
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Configuration description"
    )

    # Whether this is a public configuration (accessible to frontend)
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this is a public configuration",
    )

    # Whether this configuration item is enabled
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this configuration item is enabled",
    )

    def get_value(self) -> Any:
        """Get parsed configuration value"""
        try:
            return json.loads(self.value)
        except json.JSONDecodeError:
            # If cannot parse as JSON, return original string
            return self.value

    def set_value(self, value: Any) -> None:
        """Set configuration value, automatically convert to JSON format"""
        if isinstance(value, str):
            self.value = value
        else:
            self.value = json.dumps(value, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"<SystemConfig(key='{self.key}', value='{self.value}', is_public={self.is_public})>"
