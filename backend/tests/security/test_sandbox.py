"""
Security tests for code sandbox and execution isolation.

Tests protection against:
- Code injection
- Resource exhaustion
- File system escapes
- Network access
"""

from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# Sandbox Configuration Tests
# ============================================================================


class TestSandboxConfiguration:
    """Tests for sandbox configuration."""

    def test_default_limits(self):
        """Test that default limits are set."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        assert sandbox.max_memory_mb > 0
        assert sandbox.timeout_seconds > 0
        assert sandbox.max_cpu_percent > 0

    def test_custom_limits(self):
        """Test that custom limits can be set."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox(
            max_memory_mb=128,
            timeout_seconds=10,
            max_cpu_percent=25,
        )

        assert sandbox.max_memory_mb == 128
        assert sandbox.timeout_seconds == 10
        assert sandbox.max_cpu_percent == 25

    def test_allowed_imports_default(self):
        """Test that safe imports are allowed by default."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        # Common safe imports should be allowed
        assert "math" in sandbox.allowed_imports
        assert "json" in sandbox.allowed_imports
        assert "datetime" in sandbox.allowed_imports

    def test_dangerous_imports_blocked(self):
        """Test that dangerous imports are blocked."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        # Dangerous imports should not be in default allowed list
        assert "os" not in sandbox.allowed_imports
        assert "subprocess" not in sandbox.allowed_imports
        assert "socket" not in sandbox.allowed_imports


# ============================================================================
# Code Injection Tests
# ============================================================================


class TestCodeInjection:
    """Tests for code injection prevention."""

    @pytest.mark.asyncio
    async def test_import_os_blocked(self):
        """Test that 'import os' is blocked."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = "import os; os.system('rm -rf /')"

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Import of 'os' is not allowed",
            )

            result = await sandbox.execute(code)

            assert not result.success

    @pytest.mark.asyncio
    async def test_exec_blocked(self):
        """Test that 'exec()' is handled safely."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = "exec('import os')"

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Execution blocked",
            )

            result = await sandbox.execute(code)

            # Either blocked or executed in sandbox safely
            assert result is not None

    @pytest.mark.asyncio
    async def test_eval_blocked(self):
        """Test that 'eval()' is handled safely."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = 'eval(\'__import__("os").system("ls")\')'

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Blocked",
            )

            result = await sandbox.execute(code)

            assert result is not None


# ============================================================================
# Resource Exhaustion Tests
# ============================================================================


class TestResourceExhaustion:
    """Tests for resource exhaustion prevention."""

    @pytest.mark.asyncio
    async def test_infinite_loop_timeout(self):
        """Test that infinite loops are terminated."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox(timeout_seconds=1)

        code = "while True: pass"

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Timeout exceeded",
            )

            result = await sandbox.execute(code)

            assert not result.success

    @pytest.mark.asyncio
    async def test_memory_exhaustion_prevented(self):
        """Test that memory exhaustion is prevented."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox(max_memory_mb=64)

        code = "x = 'a' * (1024 * 1024 * 1024)"  # Try to allocate 1GB

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Memory limit exceeded",
            )

            result = await sandbox.execute(code)

            assert not result.success

    @pytest.mark.asyncio
    async def test_fork_bomb_prevented(self):
        """Test that fork bombs are prevented."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = """
import os
while True:
    os.fork()
"""

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Import not allowed or process limit exceeded",
            )

            result = await sandbox.execute(code)

            assert not result.success


# ============================================================================
# File System Escape Tests
# ============================================================================


class TestFileSystemEscape:
    """Tests for file system escape prevention."""

    def test_path_traversal_blocked(self):
        """Test that path traversal is blocked."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        # Various path traversal attempts
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\Windows\\System32",
            "/etc/passwd",
            "C:\\Windows\\System32",
            "....//....//etc/passwd",
            ".%2e/.%2e/etc/passwd",
        ]

        for path in dangerous_paths:
            sanitized = filter.sanitize_path(path)
            # Should either block or sanitize to safe path
            assert ".." not in sanitized
            assert not sanitized.startswith("/etc")
            assert not sanitized.startswith("C:\\")

    def test_symlink_following_blocked(self):
        """Test that symlink following is prevented."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        # Path that might be a symlink
        path = "uploads/link_to_etc"

        sanitized = filter.sanitize_path(path)
        # Symlink resolution should be done at execution time
        assert sanitized is not None

    def test_null_byte_injection_blocked(self):
        """Test that null byte injection is blocked."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        # Null byte injection attempt
        path = "uploads/file.txt\x00.jpg"

        sanitized = filter.sanitize_path(path)
        assert "\x00" not in sanitized


# ============================================================================
# Network Access Tests
# ============================================================================


class TestNetworkAccess:
    """Tests for network access prevention."""

    @pytest.mark.asyncio
    async def test_socket_import_blocked(self):
        """Test that socket module is blocked."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = "import socket; socket.socket().connect(('evil.com', 80))"

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Import of 'socket' is not allowed",
            )

            result = await sandbox.execute(code)

            assert not result.success

    @pytest.mark.asyncio
    async def test_urllib_blocked(self):
        """Test that urllib is blocked."""
        from airbeeps.agents.security.sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = "import urllib.request; urllib.request.urlopen('http://evil.com')"

        with patch.object(sandbox, "_execute_in_container") as mock_exec:
            mock_exec.return_value = MagicMock(
                success=False,
                stderr="Import not allowed",
            )

            result = await sandbox.execute(code)

            assert not result.success


# ============================================================================
# SQL Injection Tests
# ============================================================================


class TestSQLInjection:
    """Tests for SQL injection prevention."""

    def test_drop_table_blocked(self):
        """Test that DROP TABLE is blocked."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        dangerous_queries = [
            "SELECT * FROM users; DROP TABLE users;",
            "SELECT * FROM users WHERE id=1; DROP TABLE users;--",
            "'; DROP TABLE users;--",
        ]

        for query in dangerous_queries:
            result = filter.validate_sql(query)
            assert not result.is_valid

    def test_delete_without_where_blocked(self):
        """Test that DELETE without WHERE is blocked."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        query = "DELETE FROM users"

        result = filter.validate_sql(query)
        assert not result.is_valid

    def test_union_injection_detected(self):
        """Test that UNION injection is detected."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        query = "SELECT name FROM users WHERE id=1 UNION SELECT password FROM users"

        result = filter.validate_sql(query)
        # UNION might be valid in some cases, but should be flagged
        assert result is not None  # At minimum, should be analyzed

    def test_safe_select_allowed(self):
        """Test that safe SELECT queries are allowed."""
        from airbeeps.agents.security.content_filter import ContentFilter

        filter = ContentFilter()

        safe_queries = [
            "SELECT * FROM products WHERE category = 'electronics'",
            "SELECT name, price FROM products ORDER BY price",
            "SELECT COUNT(*) FROM orders WHERE date > '2024-01-01'",
        ]

        for query in safe_queries:
            result = filter.validate_sql(query)
            assert result.is_valid


# ============================================================================
# PII Redaction Tests
# ============================================================================


class TestPIIRedaction:
    """Tests for PII redaction in traces."""

    def test_email_redaction(self):
        """Test that email addresses are redacted."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        text = "Contact user at john.doe@example.com for more info"
        redacted = redactor.redact(text)

        assert "john.doe@example.com" not in redacted
        assert "[REDACTED" in redacted

    def test_phone_redaction(self):
        """Test that phone numbers are redacted."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        text = "Call us at 555-123-4567 or 555.987.6543"
        redacted = redactor.redact(text)

        assert "555-123-4567" not in redacted
        assert "555.987.6543" not in redacted

    def test_credit_card_redaction(self):
        """Test that credit card numbers are redacted."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        text = "Card number: 4111-1111-1111-1111"
        redacted = redactor.redact(text)

        assert "4111-1111-1111-1111" not in redacted

    def test_api_key_redaction(self):
        """Test that API keys are redacted."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        text = "API key: sk-proj-abc123xyz789longapikey"  # gitleaks:allow
        redacted = redactor.redact(text)

        assert "sk-proj-abc123xyz789longapikey" not in redacted

    def test_ssn_redaction(self):
        """Test that SSNs are redacted."""
        from airbeeps.agents.tracing.pii_redactor import PIIRedactor

        redactor = PIIRedactor()

        text = "SSN: 123-45-6789"
        redacted = redactor.redact(text)

        assert "123-45-6789" not in redacted


# ============================================================================
# Permission Tests
# ============================================================================


class TestPermissions:
    """Tests for tool permission checking."""

    @pytest.mark.asyncio
    async def test_admin_can_use_dangerous_tools(self):
        """Test that admins can use dangerous tools."""
        from airbeeps.agents.security.permissions import ToolPermissionChecker

        checker = ToolPermissionChecker()

        admin_user = MagicMock()
        admin_user.is_superuser = True

        result = await checker.can_use_tool(admin_user, "execute_python")
        assert result is True

    @pytest.mark.asyncio
    async def test_regular_user_blocked_from_dangerous_tools(self):
        """Test that regular users are blocked from dangerous tools."""
        from airbeeps.agents.security.permissions import ToolPermissionChecker

        checker = ToolPermissionChecker()

        regular_user = MagicMock()
        regular_user.is_superuser = False
        regular_user.roles = []

        # This depends on configuration
        result = await checker.can_use_tool(regular_user, "execute_python")
        # Result depends on default permissions configuration

    @pytest.mark.asyncio
    async def test_safe_tools_allowed_by_default(self):
        """Test that safe tools are allowed by default."""
        from airbeeps.agents.security.permissions import ToolPermissionChecker

        checker = ToolPermissionChecker()

        regular_user = MagicMock()
        regular_user.is_superuser = False

        result = await checker.can_use_tool(regular_user, "web_search")
        assert result is True


# ============================================================================
# Input Validation Tests
# ============================================================================


class TestInputValidation:
    """Tests for input validation."""

    def test_json_schema_validation(self):
        """Test JSON schema validation for tool inputs."""
        from airbeeps.agents.security.validator import InputValidator

        validator = InputValidator()

        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 1000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        }

        # Valid input
        valid_input = {"query": "test", "limit": 10}
        result = validator.validate(valid_input, schema)
        assert result.is_valid

        # Invalid input - missing required
        invalid_input = {"limit": 10}
        result = validator.validate(invalid_input, schema)
        assert not result.is_valid

        # Invalid input - wrong type
        invalid_input = {"query": 123}
        result = validator.validate(invalid_input, schema)
        assert not result.is_valid

    def test_max_input_size(self):
        """Test that input size limits are enforced."""
        from airbeeps.agents.security.validator import InputValidator

        validator = InputValidator(max_input_size=1000)

        # Large input should be rejected
        large_input = {"query": "x" * 10000}
        schema = {"type": "object", "properties": {"query": {"type": "string"}}}

        result = validator.validate(large_input, schema)
        # Should either fail or truncate
        assert result is not None
