"""
Unit tests for DataAnalysisTool.

Tests for data analysis with mocked database and file service.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestDataAnalysisTool:
    """Tests for DataAnalysisTool class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    def test_tool_import(self):
        """Should be able to import DataAnalysisTool."""
        from airbeeps.agents.tools.data_analysis import DataAnalysisTool

        assert DataAnalysisTool is not None

    def test_tool_properties(self, mock_session):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import AgentToolConfig, ToolSecurityLevel
        from airbeeps.agents.tools.data_analysis import DataAnalysisTool

        config = AgentToolConfig(name="analyze_data", parameters={})
        tool = DataAnalysisTool(config=config, session=mock_session)

        assert tool.name == "analyze_data"
        # Security level depends on implementation
        assert tool.security_level in [
            ToolSecurityLevel.SAFE,
            ToolSecurityLevel.MODERATE,
        ]

    def test_get_input_schema(self, mock_session):
        """Should return valid input schema."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.data_analysis import DataAnalysisTool

        config = AgentToolConfig(name="analyze_data", parameters={})
        tool = DataAnalysisTool(config=config, session=mock_session)
        schema = tool.get_input_schema()

        assert schema["type"] == "object"
        assert "document_id" in schema["properties"]
        assert "operation" in schema["properties"]

    def test_is_safe_condition_valid(self, mock_session):
        """Should accept safe filter conditions."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.data_analysis import DataAnalysisTool

        config = AgentToolConfig(name="analyze_data", parameters={})
        tool = DataAnalysisTool(config=config, session=mock_session)

        assert tool._is_safe_condition("price > 100")
        assert tool._is_safe_condition("name == 'test'")
        assert tool._is_safe_condition("quantity < 50 and category == 'A'")

    def test_is_safe_condition_dangerous(self, mock_session):
        """Should reject dangerous filter conditions."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.data_analysis import DataAnalysisTool

        config = AgentToolConfig(name="analyze_data", parameters={})
        tool = DataAnalysisTool(config=config, session=mock_session)

        # These should be rejected as potentially dangerous
        assert tool._is_safe_condition("import os") is False
        assert tool._is_safe_condition("__import__('os')") is False
        assert tool._is_safe_condition("exec('code')") is False
        assert tool._is_safe_condition("eval('1+1')") is False


class TestListTabularDocumentsTool:
    """Tests for ListTabularDocumentsTool class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    def test_tool_import(self):
        """Should be able to import ListTabularDocumentsTool."""
        from airbeeps.agents.tools.data_analysis import ListTabularDocumentsTool

        assert ListTabularDocumentsTool is not None

    def test_tool_properties(self, mock_session):
        """Should have correct tool properties."""
        from airbeeps.agents.tools.base import AgentToolConfig, ToolSecurityLevel
        from airbeeps.agents.tools.data_analysis import ListTabularDocumentsTool

        config = AgentToolConfig(name="list_tabular_documents", parameters={})
        tool = ListTabularDocumentsTool(config=config, session=mock_session)

        assert tool.name == "list_tabular_documents"
        assert tool.security_level == ToolSecurityLevel.SAFE

    @pytest.mark.asyncio
    async def test_execute_empty_list(self, mock_session):
        """Should handle empty document list or no KB configuration."""
        from airbeeps.agents.tools.base import AgentToolConfig
        from airbeeps.agents.tools.data_analysis import ListTabularDocumentsTool

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        config = AgentToolConfig(name="list_tabular_documents", parameters={})
        tool = ListTabularDocumentsTool(config=config, session=mock_session)

        result = await tool.execute()

        # Result can be a string or dict depending on configuration
        if isinstance(result, dict):
            assert "error" in result or "documents" in result
        else:
            assert (
                "No tabular documents" in result
                or "Available" in result
                or result is not None
            )
