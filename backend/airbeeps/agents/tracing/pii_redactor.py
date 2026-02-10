"""
PII Redaction for traces.

Redacts personally identifiable information before traces are exported.
This ensures GDPR compliance and prevents sensitive data leakage.
"""

import re
from typing import Any


class PIIRedactor:
    """Redact PII from trace data before export"""

    # Common PII patterns
    PATTERNS = {
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.IGNORECASE
        ),
        "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "api_key": re.compile(
            r"(?:api[_-]?key|apikey|api_secret|secret[_-]?key|auth[_-]?token|bearer)"
            r'["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})',
            re.IGNORECASE,
        ),
        "password": re.compile(
            r'(?:password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^\s"\',}{]+)',
            re.IGNORECASE,
        ),
        "jwt_token": re.compile(
            r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
        ),
        "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    }

    # Sensitive field names to redact entirely
    SENSITIVE_FIELDS = {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "api_secret",
        "token",
        "auth_token",
        "access_token",
        "refresh_token",
        "private_key",
        "secret_key",
        "credentials",
        "ssn",
        "social_security",
        "credit_card",
        "card_number",
        "cvv",
        "pin",
    }

    def __init__(
        self, enabled: bool = True, custom_patterns: dict[str, re.Pattern] | None = None
    ):
        self.enabled = enabled
        self.patterns = {**self.PATTERNS}
        if custom_patterns:
            self.patterns.update(custom_patterns)

    def redact(self, text: str) -> str:
        """Redact PII patterns from text"""
        if not self.enabled or not text:
            return text

        result = text
        for pattern_name, pattern in self.patterns.items():
            result = pattern.sub(f"[REDACTED_{pattern_name.upper()}]", result)

        return result

    def redact_dict(
        self, data: dict[str, Any], depth: int = 0, max_depth: int = 10
    ) -> dict[str, Any]:
        """Recursively redact PII from dictionary"""
        if not self.enabled or depth > max_depth:
            return data

        result = {}
        for key, value in data.items():
            # Check if field name is sensitive
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_FIELDS):
                result[key] = "[REDACTED]"
                continue

            # Recursively handle values
            if isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = [
                    self.redact_dict(item, depth + 1, max_depth)
                    if isinstance(item, dict)
                    else self.redact(item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value

        return result

    def redact_value(self, value: Any) -> Any:
        """Redact any value (string, dict, list, etc.)"""
        if not self.enabled:
            return value

        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return self.redact_dict(value)
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        return value


# Global redactor instance
_redactor: PIIRedactor | None = None


def get_redactor() -> PIIRedactor:
    """Get the global PII redactor instance"""
    global _redactor
    if _redactor is None:
        _redactor = PIIRedactor(enabled=True)
    return _redactor


def set_redactor(redactor: PIIRedactor):
    """Set the global PII redactor instance"""
    global _redactor
    _redactor = redactor
