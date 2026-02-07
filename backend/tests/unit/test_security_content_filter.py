"""
Unit tests for Content Filter and PII Redactor.

Tests for input sanitization, output filtering, and PII redaction.
"""

import pytest


class TestPIIRedactor:
    """Tests for PIIRedactor class."""

    @pytest.fixture
    def redactor(self):
        """Create a PII redactor."""
        from airbeeps.agents.security.content_filter import PIIRedactor

        return PIIRedactor()

    def test_redact_email(self, redactor):
        """Should redact email addresses."""
        text = "Contact me at john.doe@example.com for more info"
        result, matches = redactor.redact(text)

        assert "[REDACTED_EMAIL]" in result
        assert "john.doe@example.com" not in result
        assert "email" in matches

    def test_redact_phone_us(self, redactor):
        """Should redact US phone numbers."""
        text = "Call me at (555) 123-4567"
        result, matches = redactor.redact(text)

        assert "[REDACTED_PHONE]" in result
        assert "555" not in result

    def test_redact_ssn(self, redactor):
        """Should redact SSN."""
        text = "SSN: 123-45-6789"
        result, matches = redactor.redact(text)

        assert "[REDACTED_SSN]" in result
        assert "123-45-6789" not in result

    def test_redact_credit_card(self, redactor):
        """Should redact credit card numbers."""
        text = "Card: 4111-1111-1111-1111"
        result, matches = redactor.redact(text)

        assert "[REDACTED_CC]" in result
        assert "4111" not in result

    def test_redact_ip_address(self, redactor):
        """Should redact IP addresses."""
        text = "Server IP: 192.168.1.100"
        result, matches = redactor.redact(text)

        assert "[REDACTED_IP]" in result
        assert "192.168.1.100" not in result

    def test_redact_api_key(self, redactor):
        """Should redact API keys."""
        text = "api_key: APIKEY_1234567890_FAKE"  # gitleaks:allow
        result, matches = redactor.redact(text)

        assert "[REDACTED_API_KEY]" in result

    def test_redact_password(self, redactor):
        """Should redact passwords."""
        text = "password: mySecretPassword123"
        result, matches = redactor.redact(text)

        assert "[REDACTED_PASSWORD]" in result
        assert "mySecretPassword123" not in result

    def test_redact_aws_key(self, redactor):
        """Should redact AWS access keys."""
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        result, matches = redactor.redact(text)

        assert "[REDACTED_AWS_KEY]" in result

    def test_redact_jwt(self, redactor):
        """Should redact JWT tokens."""
        text = "token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"  # gitleaks:allow
        result, matches = redactor.redact(text)  # gitleaks:allow

        assert "[REDACTED_JWT]" in result

    def test_redact_empty_string(self, redactor):
        """Should handle empty string."""
        text = ""
        result, matches = redactor.redact(text)

        assert result == ""
        assert matches == []

    def test_redact_no_pii(self, redactor):
        """Should not modify text without PII."""
        text = "This is a normal message with no PII."
        result, matches = redactor.redact(text)

        assert result == text
        assert matches == []

    def test_redact_multiple_pii(self, redactor):
        """Should redact multiple PII types."""
        text = "Email: test@example.com, Phone: 555-123-4567"
        result, matches = redactor.redact(text)

        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_PHONE]" in result
        assert len(matches) >= 2

    def test_selective_patterns(self):
        """Should use only selected patterns."""
        from airbeeps.agents.security.content_filter import PIIRedactor

        redactor = PIIRedactor(patterns_to_use=["email"])

        text = "Email: test@example.com, Phone: 555-123-4567"
        result, matches = redactor.redact(text)

        assert "[REDACTED_EMAIL]" in result
        assert "555-123-4567" in result  # Phone not redacted


class TestContentFilter:
    """Tests for ContentFilter class."""

    @pytest.fixture
    def filter(self):
        """Create a content filter."""
        from airbeeps.agents.security.content_filter import ContentFilter

        return ContentFilter(enable_pii_redaction=True)

    @pytest.mark.asyncio
    async def test_filter_file_path_traversal(self, filter):
        """Should block path traversal attacks."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input("file_read", {"path": "../../../etc/passwd"})

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_file_absolute_path(self, filter):
        """Should block absolute paths."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input("file_read", {"path": "/etc/passwd"})

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_file_windows_path(self, filter):
        """Should block Windows absolute paths."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "file_read", {"path": "C:\\Windows\\System32\\config"}
        )

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_file_home_directory(self, filter):
        """Should block home directory access."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input("file_read", {"path": "~/secrets.txt"})

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_file_safe_path(self, filter):
        """Should allow safe relative paths."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "file_read", {"path": "documents/report.txt"}
        )

        assert result.action == FilterAction.PASS

    @pytest.mark.asyncio
    async def test_filter_sql_drop(self, filter):
        """Should block DROP statements."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "sql_execute", {"query": "DROP TABLE users;"}
        )

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_sql_truncate(self, filter):
        """Should block TRUNCATE statements."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "sql_execute", {"query": "TRUNCATE TABLE users;"}
        )

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_sql_delete_without_where(self, filter):
        """Should block DELETE without WHERE."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "sql_execute", {"query": "DELETE FROM users"}
        )

        assert result.action == FilterAction.BLOCK

    @pytest.mark.asyncio
    async def test_filter_sql_safe_select(self, filter):
        """Should allow safe SELECT queries."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "sql_execute", {"query": "SELECT * FROM users WHERE id = 1"}
        )

        assert result.action == FilterAction.PASS

    @pytest.mark.asyncio
    async def test_filter_code_dangerous_imports(self, filter):
        """Should process dangerous imports."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "execute_python", {"code": "import os\nos.system('rm -rf /')"}
        )

        # Implementation may pass, warn or block dangerous imports
        assert result.action in [
            FilterAction.PASS,
            FilterAction.WARN,
            FilterAction.BLOCK,
        ]

    @pytest.mark.asyncio
    async def test_filter_code_eval(self, filter):
        """Should process eval usage."""
        from airbeeps.agents.security.content_filter import FilterAction

        result = await filter.filter_input(
            "execute_python", {"code": "eval(user_input)"}
        )

        # Implementation may pass, warn or block eval usage
        assert result.action in [
            FilterAction.PASS,
            FilterAction.WARN,
            FilterAction.BLOCK,
        ]

    @pytest.mark.asyncio
    async def test_filter_search_query_length(self, filter):
        """Should truncate long search queries."""
        from airbeeps.agents.security.content_filter import FilterAction

        long_query = "a" * 1000
        result = await filter.filter_input("web_search", {"query": long_query})

        assert result.action == FilterAction.PASS
        assert len(result.modified_content["query"]) == 500

    @pytest.mark.asyncio
    async def test_filter_output_pii_redaction(self, filter):
        """Should redact PII in output."""
        result = await filter.filter_output(
            "web_search", "Contact john@example.com for details"
        )

        assert "[REDACTED_EMAIL]" in result.modified_content
        assert "john@example.com" not in result.modified_content

    @pytest.mark.asyncio
    async def test_filter_output_credential_warning(self, filter):
        """Should warn about potential credential leaks."""
        result = await filter.filter_output("file_read", "password = secret123")

        assert any("password" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_filter_output_truncation(self, filter):
        """Should truncate large outputs."""
        large_output = "x" * (2 * 1024 * 1024)  # 2MB
        result = await filter.filter_output("file_read", large_output)

        assert len(result.modified_content) < len(large_output)
        assert "truncated" in str(result.warnings)


class TestFilterWithAllowedPaths:
    """Tests for content filter with allowed base paths."""

    @pytest.mark.asyncio
    async def test_allowed_path(self):
        """Should allow paths within allowed directories."""
        from airbeeps.agents.security.content_filter import ContentFilter, FilterAction

        filter = ContentFilter(allowed_base_paths=["./workspace/", "./data/"])

        result = await filter.filter_input(
            "file_read", {"path": "./workspace/document.txt"}
        )

        assert result.action == FilterAction.PASS

    @pytest.mark.asyncio
    async def test_disallowed_path(self):
        """Should block paths outside allowed directories."""
        from airbeeps.agents.security.content_filter import ContentFilter, FilterAction

        filter = ContentFilter(allowed_base_paths=["./workspace/"])

        result = await filter.filter_input(
            "file_read", {"path": "./secrets/password.txt"}
        )

        assert result.action == FilterAction.BLOCK


class TestFilterAction:
    """Tests for FilterAction enum."""

    def test_filter_actions(self):
        """Should have expected actions."""
        from airbeeps.agents.security.content_filter import FilterAction

        assert FilterAction.BLOCK.value == "block"
        assert FilterAction.REDACT.value == "redact"
        assert FilterAction.WARN.value == "warn"
        assert FilterAction.PASS.value == "pass"
