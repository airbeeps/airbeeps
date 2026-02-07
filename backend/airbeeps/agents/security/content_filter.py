"""
Content filtering for agent tool inputs and outputs.

Provides:
- Input sanitization (path traversal, injection prevention)
- Output filtering (credential detection, PII redaction)
- SQL query validation
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FilterAction(str, Enum):
    """Action to take when filter matches"""

    BLOCK = "block"  # Block the entire request/response
    REDACT = "redact"  # Redact the matched content
    WARN = "warn"  # Allow but log a warning
    PASS = "pass"  # Allow without modification


@dataclass
class FilterResult:
    """Result of content filtering"""

    action: FilterAction
    modified_content: Any = None
    matches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PIIRedactor:
    """Redact personally identifiable information from text"""

    # PII patterns
    PATTERNS = {
        "email": (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "[REDACTED_EMAIL]",
        ),
        "phone_us": (
            r"\b(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            "[REDACTED_PHONE]",
        ),
        "phone_intl": (
            r"\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b",
            "[REDACTED_PHONE]",
        ),
        "ssn": (r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b", "[REDACTED_SSN]"),
        "credit_card": (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[REDACTED_CC]"),
        "ip_address": (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[REDACTED_IP]"),
        "api_key": (
            r"(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token)[\"\':\s]*[=:]?\s*[\"\'`]?([a-zA-Z0-9_\-]{20,})[\"\'`]?",
            "[REDACTED_API_KEY]",
        ),
        "password": (
            r"(?i)(password|passwd|pwd)[\"\':\s]*[=:]?\s*[\"\'`]?([^\s\"\'`]{8,})[\"\'`]?",
            "[REDACTED_PASSWORD]",
        ),
        "aws_key": (r"\b(AKIA[0-9A-Z]{16})\b", "[REDACTED_AWS_KEY]"),
        "jwt": (
            r"\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b",
            "[REDACTED_JWT]",
        ),
    }

    def __init__(self, patterns_to_use: list[str] | None = None):
        """
        Initialize PII redactor.

        Args:
            patterns_to_use: List of pattern names to use, or None for all
        """
        if patterns_to_use:
            self.patterns = {
                k: v for k, v in self.PATTERNS.items() if k in patterns_to_use
            }
        else:
            self.patterns = self.PATTERNS.copy()

    def redact(self, text: str) -> tuple[str, list[str]]:
        """
        Redact PII from text.

        Returns:
            Tuple of (redacted_text, list_of_matched_pattern_names)
        """
        if not text:
            return text, []

        matches = []
        result = text

        for pattern_name, (pattern, replacement) in self.patterns.items():
            if re.search(pattern, result):
                matches.append(pattern_name)
                result = re.sub(pattern, replacement, result)

        return result, matches


class ContentFilter:
    """
    Filter and sanitize tool inputs and outputs.

    Provides security validation for:
    - File paths (prevent traversal)
    - SQL queries (prevent injection)
    - Shell commands (prevent injection)
    - General input/output sanitization
    """

    def __init__(
        self,
        enable_pii_redaction: bool = True,
        allowed_base_paths: list[str] | None = None,
    ):
        self.pii_redactor = PIIRedactor() if enable_pii_redaction else None
        self.allowed_base_paths = allowed_base_paths or []

    async def filter_input(
        self,
        tool_name: str,
        input_data: dict[str, Any],
    ) -> FilterResult:
        """
        Filter tool input before execution.

        Args:
            tool_name: Name of the tool
            input_data: Input parameters for the tool

        Returns:
            FilterResult with action and modified data
        """
        warnings = []
        modified_data = input_data.copy()

        # Tool-specific filters
        if tool_name in ["file_read", "file_write", "file_operations"]:
            result = self._filter_file_path(modified_data)
            if result.action == FilterAction.BLOCK:
                return result
            modified_data = result.modified_content
            warnings.extend(result.warnings)

        elif tool_name in ["sql_execute", "database_query"]:
            result = self._filter_sql_query(modified_data)
            if result.action == FilterAction.BLOCK:
                return result
            modified_data = result.modified_content
            warnings.extend(result.warnings)

        elif tool_name in ["execute_python", "code_executor"]:
            result = self._filter_code(modified_data)
            if result.action == FilterAction.BLOCK:
                return result
            modified_data = result.modified_content
            warnings.extend(result.warnings)

        elif tool_name in ["web_search"]:
            result = self._filter_search_query(modified_data)
            if result.action == FilterAction.BLOCK:
                return result
            modified_data = result.modified_content
            warnings.extend(result.warnings)

        return FilterResult(
            action=FilterAction.PASS,
            modified_content=modified_data,
            warnings=warnings,
        )

    async def filter_output(
        self,
        tool_name: str,
        output: Any,
    ) -> FilterResult:
        """
        Filter tool output before returning to user.

        Args:
            tool_name: Name of the tool
            output: Output from the tool

        Returns:
            FilterResult with action and modified output
        """
        warnings = []
        matches = []

        # Convert to string for filtering
        output_str = str(output) if output else ""

        # Check for credential leaks
        credential_patterns = [
            (r"(?i)password\s*[:=]\s*\S+", "Possible password leak"),
            (r"(?i)api[_-]?key\s*[:=]\s*\S+", "Possible API key leak"),
            (r"(?i)secret\s*[:=]\s*\S+", "Possible secret leak"),
            (r"(?i)token\s*[:=]\s*\S+", "Possible token leak"),
        ]

        for pattern, warning in credential_patterns:
            if re.search(pattern, output_str):
                warnings.append(warning)

        # Check output size
        max_size = 1024 * 1024  # 1MB
        if len(output_str) > max_size:
            output_str = output_str[:max_size] + "\n... (output truncated)"
            warnings.append(f"Output truncated to {max_size} bytes")

        # PII redaction
        if self.pii_redactor:
            output_str, pii_matches = self.pii_redactor.redact(output_str)
            if pii_matches:
                matches.extend(pii_matches)
                warnings.append(f"PII redacted: {', '.join(pii_matches)}")

        return FilterResult(
            action=FilterAction.PASS,
            modified_content=output_str,
            matches=matches,
            warnings=warnings,
        )

    def _filter_file_path(self, data: dict[str, Any]) -> FilterResult:
        """Filter file path inputs for path traversal attacks"""
        path = data.get("path", data.get("file_path", ""))

        if not path:
            return FilterResult(action=FilterAction.PASS, modified_content=data)

        # Check for path traversal patterns
        dangerous_patterns = [
            r"\.\./",  # ../
            r"\.\.\\",  # ..\
            r"^/",  # Absolute path starting with /
            r"^[A-Za-z]:",  # Windows absolute path
            r"~",  # Home directory
            r"\$\{",  # Variable expansion
            r"\$\(",  # Command substitution
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, path):
                return FilterResult(
                    action=FilterAction.BLOCK,
                    matches=[pattern],
                    warnings=[f"Dangerous path pattern detected: {pattern}"],
                )

        # Validate against allowed base paths
        if self.allowed_base_paths:
            path_allowed = False
            for base_path in self.allowed_base_paths:
                if path.startswith(base_path):
                    path_allowed = True
                    break

            if not path_allowed:
                return FilterResult(
                    action=FilterAction.BLOCK,
                    warnings=[f"Path '{path}' is outside allowed directories"],
                )

        return FilterResult(action=FilterAction.PASS, modified_content=data)

    def _filter_sql_query(self, data: dict[str, Any]) -> FilterResult:
        """Filter SQL queries for injection and dangerous operations"""
        query = data.get("query", data.get("sql", ""))

        if not query:
            return FilterResult(action=FilterAction.PASS, modified_content=data)

        query_upper = query.upper()

        # Block dangerous DDL operations
        dangerous_patterns = [
            (r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX)\b", "DROP operation not allowed"),
            (r"\bTRUNCATE\s+TABLE\b", "TRUNCATE not allowed"),
            (r"\bALTER\s+(TABLE|DATABASE)\b", "ALTER operation not allowed"),
            (r"\bCREATE\s+(TABLE|DATABASE|SCHEMA)\b", "CREATE operation not allowed"),
            (r"\bDELETE\s+FROM\s+\w+\s*$", "DELETE without WHERE clause not allowed"),
            (
                r"\bUPDATE\s+\w+\s+SET\s+.*(?!WHERE)",
                "UPDATE without WHERE clause not allowed",
            ),
            (
                r";\s*(DROP|DELETE|UPDATE|ALTER|CREATE)",
                "Multiple statements not allowed",
            ),
            (r"--", "SQL comments not allowed"),
            (r"/\*.*\*/", "Block comments not allowed"),
            (r"\bEXEC\b|\bEXECUTE\b", "EXEC not allowed"),
            (r"\bxp_", "Extended stored procedures not allowed"),
        ]

        for pattern, message in dangerous_patterns:
            if re.search(pattern, query_upper):
                return FilterResult(
                    action=FilterAction.BLOCK,
                    matches=[pattern],
                    warnings=[message],
                )

        return FilterResult(action=FilterAction.PASS, modified_content=data)

    def _filter_code(self, data: dict[str, Any]) -> FilterResult:
        """Filter code for dangerous patterns"""
        code = data.get("code", "")

        if not code:
            return FilterResult(action=FilterAction.PASS, modified_content=data)

        # These are just warnings - actual blocking is done by the sandbox
        warnings = []

        dangerous_patterns = [
            (r"\bimport\s+os\b", "os module usage detected"),
            (r"\bimport\s+subprocess\b", "subprocess module usage detected"),
            (r"\bimport\s+sys\b", "sys module usage detected"),
            (r"\bopen\s*\(", "file open operation detected"),
            (r"\beval\s*\(", "eval function detected"),
            (r"\bexec\s*\(", "exec function detected"),
            (r"\b__import__\s*\(", "__import__ function detected"),
        ]

        for pattern, warning in dangerous_patterns:
            if re.search(pattern, code):
                warnings.append(warning)

        return FilterResult(
            action=FilterAction.WARN if warnings else FilterAction.PASS,
            modified_content=data,
            warnings=warnings,
        )

    def _filter_search_query(self, data: dict[str, Any]) -> FilterResult:
        """Filter search queries"""
        query = data.get("query", "")

        if not query:
            return FilterResult(action=FilterAction.PASS, modified_content=data)

        # Limit query length
        max_length = 500
        if len(query) > max_length:
            data = data.copy()
            data["query"] = query[:max_length]
            return FilterResult(
                action=FilterAction.PASS,
                modified_content=data,
                warnings=[f"Query truncated to {max_length} characters"],
            )

        return FilterResult(action=FilterAction.PASS, modified_content=data)
