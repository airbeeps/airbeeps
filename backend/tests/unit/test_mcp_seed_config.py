"""
Tests for MCP server seed configuration (Phase 3).

Tests that MCP servers (GitHub, Notion, Google Drive, etc.) are properly
configured in seed.yaml with required fields and setup instructions.
"""

from pathlib import Path

import pytest
import yaml


class TestMCPSeedConfiguration:
    """Tests for MCP server seed configuration."""

    @pytest.fixture
    def seed_config(self):
        """Load the seed.yaml configuration."""
        seed_path = (
            Path(__file__).parent.parent.parent / "airbeeps" / "config" / "seed.yaml"
        )
        assert seed_path.exists(), f"seed.yaml not found at {seed_path}"

        with open(seed_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def mcp_servers(self, seed_config):
        """Extract MCP servers from seed config."""
        servers = seed_config.get("mcp_servers", [])
        assert len(servers) > 0, "No MCP servers found in seed.yaml"
        return servers

    def test_mcp_servers_exist(self, mcp_servers):
        """Test that MCP servers are defined in seed.yaml."""
        assert len(mcp_servers) >= 3, (
            "Should have at least GitHub, Notion, Google Drive"
        )

    def test_github_server_config(self, mcp_servers):
        """Test GitHub MCP server configuration."""
        github = next((s for s in mcp_servers if s["name"] == "github"), None)
        assert github is not None, "GitHub MCP server should exist"

        # Required fields
        assert github["display_name"] == "GitHub"
        assert github["server_type"] == "STDIO"
        assert github["is_active"] is False, "Should be disabled by default"

        # Connection config
        conn = github["connection_config"]
        assert conn["command"] == "npx"
        assert "@modelcontextprotocol/server-github" in conn["args"]
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in conn.get("env", {})

        # Extra data with setup instructions
        extra = github.get("extra_data", {})
        assert "setup_instructions" in extra
        assert "required_env_vars" in extra
        assert any(v["name"] == "GITHUB_TOKEN" for v in extra["required_env_vars"])

    def test_notion_server_config(self, mcp_servers):
        """Test Notion MCP server configuration."""
        notion = next((s for s in mcp_servers if s["name"] == "notion"), None)
        assert notion is not None, "Notion MCP server should exist"

        # Required fields
        assert notion["display_name"] == "Notion"
        assert notion["server_type"] == "STDIO"
        assert notion["is_active"] is False, "Should be disabled by default"

        # Connection config
        conn = notion["connection_config"]
        assert conn["command"] == "npx"
        assert any("notion" in arg.lower() for arg in conn["args"])

        # Extra data with setup instructions
        extra = notion.get("extra_data", {})
        assert "setup_instructions" in extra
        assert "required_env_vars" in extra
        assert any("NOTION" in v["name"] for v in extra["required_env_vars"])

    def test_google_drive_server_config(self, mcp_servers):
        """Test Google Drive MCP server configuration."""
        gdrive = next((s for s in mcp_servers if s["name"] == "google-drive"), None)
        assert gdrive is not None, "Google Drive MCP server should exist"

        # Required fields
        assert gdrive["display_name"] == "Google Drive"
        assert gdrive["server_type"] == "STDIO"
        assert gdrive["is_active"] is False, "Should be disabled by default"

        # Connection config
        conn = gdrive["connection_config"]
        assert conn["command"] == "npx"
        assert any("gdrive" in arg.lower() for arg in conn["args"])
        assert "GOOGLE_APPLICATION_CREDENTIALS" in conn.get("env", {})

        # Extra data with setup instructions
        extra = gdrive.get("extra_data", {})
        assert "setup_instructions" in extra
        assert "required_env_vars" in extra

    def test_all_servers_have_required_fields(self, mcp_servers):
        """Test that all MCP servers have required fields."""
        required_fields = [
            "name",
            "display_name",
            "server_type",
            "connection_config",
            "is_active",
        ]

        for server in mcp_servers:
            for field in required_fields:
                assert field in server, (
                    f"Server {server.get('name', 'unknown')} missing {field}"
                )

    def test_all_servers_disabled_by_default(self, mcp_servers):
        """Test that all MCP servers are disabled by default (require user config)."""
        for server in mcp_servers:
            # Servers requiring API keys should be disabled by default
            conn = server.get("connection_config", {})
            env_vars = conn.get("env", {})

            if env_vars:  # Has environment variables (likely requires API key)
                assert server["is_active"] is False, (
                    f"Server {server['name']} with env vars should be disabled by default"
                )

    def test_connection_config_structure(self, mcp_servers):
        """Test that connection configs have proper structure for STDIO servers."""
        for server in mcp_servers:
            if server["server_type"] == "STDIO":
                conn = server["connection_config"]
                assert "command" in conn, f"STDIO server {server['name']} needs command"
                assert "args" in conn, f"STDIO server {server['name']} needs args"
                assert isinstance(conn["args"], list), "args should be a list"

    def test_setup_instructions_present(self, mcp_servers):
        """Test that servers with env vars have setup instructions."""
        for server in mcp_servers:
            conn = server.get("connection_config", {})
            env_vars = conn.get("env", {})

            if env_vars:
                extra = server.get("extra_data", {})
                assert "setup_instructions" in extra, (
                    f"Server {server['name']} with env vars needs setup_instructions"
                )
                assert len(extra["setup_instructions"]) > 50, (
                    f"Server {server['name']} setup_instructions seems too short"
                )

    def test_required_env_vars_documented(self, mcp_servers):
        """Test that required environment variables are documented."""
        for server in mcp_servers:
            conn = server.get("connection_config", {})
            env_vars = conn.get("env", {})

            if env_vars:
                extra = server.get("extra_data", {})
                required_vars = extra.get("required_env_vars", [])

                assert len(required_vars) > 0, (
                    f"Server {server['name']} should document required_env_vars"
                )

                for var in required_vars:
                    assert "name" in var, "Each env var needs a name"
                    assert "description" in var, "Each env var needs a description"

    def test_server_categories(self, mcp_servers):
        """Test that servers have appropriate categories."""
        valid_categories = {
            "developer",
            "productivity",
            "search",
            "data",
            "communication",
            "storage",
            "system",
            "database",
        }

        for server in mcp_servers:
            extra = server.get("extra_data", {})
            category = extra.get("category")

            if category:
                assert category in valid_categories, (
                    f"Server {server['name']} has invalid category: {category}"
                )


class TestMCPServerNames:
    """Tests for MCP server naming conventions."""

    @pytest.fixture
    def mcp_servers(self):
        """Load MCP servers from seed.yaml."""
        seed_path = (
            Path(__file__).parent.parent.parent / "airbeeps" / "config" / "seed.yaml"
        )
        with open(seed_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("mcp_servers", [])

    def test_unique_server_names(self, mcp_servers):
        """Test that all server names are unique."""
        names = [s["name"] for s in mcp_servers]
        assert len(names) == len(set(names)), "Server names must be unique"

    def test_server_name_format(self, mcp_servers):
        """Test that server names follow kebab-case convention."""
        import re

        kebab_pattern = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

        for server in mcp_servers:
            name = server["name"]
            assert kebab_pattern.match(name), (
                f"Server name '{name}' should be kebab-case (e.g., 'google-drive')"
            )

    def test_display_names_readable(self, mcp_servers):
        """Test that display names are human-readable."""
        for server in mcp_servers:
            display_name = server["display_name"]
            assert len(display_name) >= 3, "Display name too short"
            assert display_name[0].isupper(), "Display name should start with uppercase"


class TestLiveConnectorIntegration:
    """Tests for live connector integration requirements."""

    @pytest.fixture
    def mcp_servers(self):
        """Load MCP servers from seed.yaml."""
        seed_path = (
            Path(__file__).parent.parent.parent / "airbeeps" / "config" / "seed.yaml"
        )
        with open(seed_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("mcp_servers", [])

    def test_primary_connectors_exist(self, mcp_servers):
        """Test that primary live connectors (GitHub, Notion, Google Drive) exist."""
        server_names = {s["name"] for s in mcp_servers}

        required = {"github", "notion", "google-drive"}
        missing = required - server_names

        assert not missing, f"Missing required connectors: {missing}"

    def test_connectors_have_icons(self, mcp_servers):
        """Test that connectors have icons for UI display."""
        for server in mcp_servers:
            extra = server.get("extra_data", {})
            # Icon is optional but recommended
            if server["name"] in {"github", "notion", "google-drive"}:
                assert "icon" in extra, (
                    f"Primary connector {server['name']} should have an icon"
                )

    def test_env_var_placeholders(self, mcp_servers):
        """Test that env var values use proper placeholder syntax."""
        import re

        placeholder_pattern = re.compile(r"\$\{[A-Z_]+\}")

        for server in mcp_servers:
            conn = server.get("connection_config", {})
            env_vars = conn.get("env", {})

            for key, value in env_vars.items():
                if isinstance(value, str) and "${" in value:
                    # Check for proper placeholder format
                    matches = placeholder_pattern.findall(value)
                    assert len(matches) > 0, (
                        f"Invalid placeholder in {server['name']}.{key}: {value}"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
