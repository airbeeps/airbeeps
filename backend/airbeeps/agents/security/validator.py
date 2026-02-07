"""
Input/Output validation for agent tools.

Provides:
- Schema-based input validation
- Output size and type validation
- Rate limiting checks
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation"""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_data: Any = None


class InputValidator:
    """
    Validate tool inputs against expected schemas.
    """

    # Default limits
    DEFAULT_MAX_STRING_LENGTH = 10000
    DEFAULT_MAX_ARRAY_LENGTH = 100
    DEFAULT_MAX_OBJECT_DEPTH = 5

    def __init__(
        self,
        max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
        max_array_length: int = DEFAULT_MAX_ARRAY_LENGTH,
        max_object_depth: int = DEFAULT_MAX_OBJECT_DEPTH,
    ):
        self.max_string_length = max_string_length
        self.max_array_length = max_array_length
        self.max_object_depth = max_object_depth

    def validate(
        self,
        data: dict[str, Any],
        schema: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Validate input data.

        Args:
            data: Input data to validate
            schema: Optional JSON schema to validate against

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []
        sanitized = {}

        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                errors=["Input must be a dictionary"],
            )

        # Validate each field
        for key, value in data.items():
            field_result = self._validate_field(key, value, depth=0)

            if not field_result.valid:
                errors.extend(field_result.errors)
            else:
                sanitized[key] = field_result.sanitized_data

            warnings.extend(field_result.warnings)

        # Schema validation if provided
        if schema:
            schema_result = self._validate_schema(data, schema)
            errors.extend(schema_result.errors)
            warnings.extend(schema_result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_data=sanitized if len(errors) == 0 else None,
        )

    def _validate_field(
        self,
        key: str,
        value: Any,
        depth: int,
    ) -> ValidationResult:
        """Validate a single field"""
        warnings = []

        # Check depth
        if depth > self.max_object_depth:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Field '{key}' exceeds maximum nesting depth ({self.max_object_depth})"
                ],
            )

        # String validation
        if isinstance(value, str):
            if len(value) > self.max_string_length:
                warnings.append(
                    f"Field '{key}' truncated from {len(value)} to {self.max_string_length} characters"
                )
                value = value[: self.max_string_length]

            return ValidationResult(valid=True, warnings=warnings, sanitized_data=value)

        # List validation
        if isinstance(value, list):
            if len(value) > self.max_array_length:
                return ValidationResult(
                    valid=False,
                    errors=[
                        f"Field '{key}' exceeds maximum array length ({self.max_array_length})"
                    ],
                )

            sanitized_list = []
            for i, item in enumerate(value):
                item_result = self._validate_field(f"{key}[{i}]", item, depth + 1)
                if not item_result.valid:
                    return item_result
                sanitized_list.append(item_result.sanitized_data)
                warnings.extend(item_result.warnings)

            return ValidationResult(
                valid=True, warnings=warnings, sanitized_data=sanitized_list
            )

        # Dict validation
        if isinstance(value, dict):
            sanitized_dict = {}
            for k, v in value.items():
                item_result = self._validate_field(f"{key}.{k}", v, depth + 1)
                if not item_result.valid:
                    return item_result
                sanitized_dict[k] = item_result.sanitized_data
                warnings.extend(item_result.warnings)

            return ValidationResult(
                valid=True, warnings=warnings, sanitized_data=sanitized_dict
            )

        # Primitive types (int, float, bool, None) - pass through
        if value is None or isinstance(value, (int, float, bool)):
            return ValidationResult(valid=True, sanitized_data=value)

        # Unknown type
        return ValidationResult(
            valid=False,
            errors=[f"Field '{key}' has unsupported type: {type(value).__name__}"],
        )

    def _validate_schema(
        self,
        data: dict[str, Any],
        schema: dict[str, Any],
    ) -> ValidationResult:
        """Validate data against JSON schema"""
        errors = []
        warnings = []

        # Get required fields
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for field_name in required:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        # Validate field types
        for field_name, field_schema in properties.items():
            if field_name not in data:
                continue

            value = data[field_name]
            expected_type = field_schema.get("type")

            if expected_type:
                type_valid = self._check_type(value, expected_type)
                if not type_valid:
                    errors.append(
                        f"Field '{field_name}' expected type '{expected_type}', "
                        f"got '{type(value).__name__}'"
                    )

            # Check enum values
            enum_values = field_schema.get("enum")
            if enum_values and value not in enum_values:
                errors.append(f"Field '{field_name}' must be one of: {enum_values}")

            # Check min/max for numbers
            if isinstance(value, (int, float)):
                minimum = field_schema.get("minimum")
                maximum = field_schema.get("maximum")

                if minimum is not None and value < minimum:
                    errors.append(f"Field '{field_name}' must be >= {minimum}")
                if maximum is not None and value > maximum:
                    errors.append(f"Field '{field_name}' must be <= {maximum}")

            # Check minLength/maxLength for strings
            if isinstance(value, str):
                min_length = field_schema.get("minLength")
                max_length = field_schema.get("maxLength")

                if min_length is not None and len(value) < min_length:
                    errors.append(
                        f"Field '{field_name}' must be at least {min_length} characters"
                    )
                if max_length is not None and len(value) > max_length:
                    errors.append(
                        f"Field '{field_name}' must be at most {max_length} characters"
                    )

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON schema type"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        expected_python_type = type_map.get(expected_type)
        if expected_python_type is None:
            return True  # Unknown type, assume valid

        return isinstance(value, expected_python_type)


class OutputValidator:
    """
    Validate tool outputs.
    """

    DEFAULT_MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB

    def __init__(
        self,
        max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE,
    ):
        self.max_output_size = max_output_size

    def validate(self, output: Any) -> ValidationResult:
        """
        Validate tool output.

        Args:
            output: Output to validate

        Returns:
            ValidationResult with validation status
        """
        warnings = []

        # Convert to string for size check
        output_str = str(output) if output is not None else ""

        # Check size
        if len(output_str) > self.max_output_size:
            # Truncate
            output_str = output_str[: self.max_output_size]
            warnings.append(f"Output truncated to {self.max_output_size} bytes")

        # Check for null bytes (binary content)
        if "\x00" in output_str:
            return ValidationResult(
                valid=False,
                errors=["Output contains binary data"],
            )

        return ValidationResult(
            valid=True,
            warnings=warnings,
            sanitized_data=output_str,
        )

    def validate_json(self, output: Any) -> ValidationResult:
        """
        Validate that output is JSON-serializable.
        """
        import json

        try:
            json.dumps(output)
            return ValidationResult(valid=True, sanitized_data=output)
        except (TypeError, ValueError) as e:
            return ValidationResult(
                valid=False,
                errors=[f"Output is not JSON-serializable: {e}"],
            )
