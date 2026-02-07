# MCP Integration Guide

This guide covers how to integrate Model Context Protocol (MCP) servers with Airbeeps.

## Table of Contents

- [Overview](#overview)
- [Recommended MCP Servers](#recommended-mcp-servers)
- [Adding MCP Servers](#adding-mcp-servers)
- [Creating Custom MCP Servers](#creating-custom-mcp-servers)
- [Security Considerations](#security-considerations)
- [Deployment Patterns](#deployment-patterns)
- [Troubleshooting](#troubleshooting)

---

## Overview

MCP (Model Context Protocol) is a standard for connecting AI assistants to external tools and data sources. Airbeeps supports MCP servers to extend agent capabilities.

### Key Concepts

| Concept        | Description                                |
| -------------- | ------------------------------------------ |
| **MCP Server** | External process providing tools/resources |
| **Tools**      | Functions the agent can call               |
| **Resources**  | Read-only data sources                     |
| **Prompts**    | Pre-defined prompt templates               |

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Airbeeps Backend                      │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Agent Executor │  │  MCP Registry   │              │
│  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                        │
│           │    ┌───────────────┘                        │
│           │    │                                        │
│  ┌────────▼────▼────────┐                              │
│  │     MCP Client       │                              │
│  │ (airbeeps.agents.mcp)│                              │
│  └──────────┬───────────┘                              │
└─────────────┼───────────────────────────────────────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│Brave  │ │SQLite │ │Custom │
│Search │ │Server │ │Server │
└───────┘ └───────┘ └───────┘
```

---

## Recommended MCP Servers

### Official Servers

| Server           | Package                                     | Security  | Description      |
| ---------------- | ------------------------------------------- | --------- | ---------------- |
| **Brave Search** | `@modelcontextprotocol/server-brave-search` | SAFE      | Web search       |
| **Filesystem**   | `@modelcontextprotocol/server-filesystem`   | DANGEROUS | File operations  |
| **SQLite**       | `@modelcontextprotocol/server-sqlite`       | MODERATE  | Database queries |
| **GitHub**       | `@modelcontextprotocol/server-github`       | MODERATE  | GitHub API       |
| **Slack**        | `@modelcontextprotocol/server-slack`        | MODERATE  | Slack API        |
| **Notion**       | `@notionhq/notion-mcp-server`               | MODERATE  | Notion API       |
| **Google Drive** | `@modelcontextprotocol/server-gdrive`       | MODERATE  | Google Drive     |

### Installing Official Servers

```bash
# Node.js servers (npx)
npx @modelcontextprotocol/server-brave-search
npx @modelcontextprotocol/server-filesystem /path/to/allowed/directory
npx @modelcontextprotocol/server-sqlite /path/to/database.db

# Python servers (uvx)
uvx mcp-server-fetch
uvx mcp-server-memory
```

---

## Pre-configured Connectors

Airbeeps comes with pre-configured MCP servers for popular services. These are disabled by default and require you to set up the appropriate credentials.

### GitHub Connector

Access GitHub repositories, issues, pull requests, and code search.

**Setup:**

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Generate a new token (classic) with scopes: `repo`, `read:user`
3. Set the environment variable:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

**Available Tools:**
- `search_repositories` - Search GitHub repositories
- `get_file_contents` - Read file contents from a repository
- `search_code` - Search code across repositories
- `list_issues` - List issues in a repository
- `get_pull_request` - Get pull request details

### Notion Connector

Query Notion pages and databases for knowledge retrieval.

**Setup:**

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Create a new internal integration
3. Copy the Internal Integration Token
4. Share your pages/databases with the integration (click "Share" on each page and add your integration)
5. Set the environment variable:

```bash
export NOTION_API_KEY=secret_xxxxxxxxxxxx
```

**Available Tools:**
- `search_pages` - Search across Notion pages
- `get_page` - Get page content
- `query_database` - Query a Notion database
- `list_databases` - List available databases

### Google Drive Connector

Search and read files from Google Drive.

**Setup:**

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Drive API
3. Create a service account and download the JSON credentials file
4. Share folders/files with the service account email
5. Set the environment variable:

```bash
export GOOGLE_CREDENTIALS_PATH=/path/to/service-account.json
```

**Available Tools:**
- `search_files` - Search files by name or content
- `get_file` - Download file contents
- `list_files` - List files in a folder

### Brave Search Connector

Web search using the privacy-respecting Brave Search API.

**Setup:**

1. Sign up at [Brave Search API](https://brave.com/search/api/)
2. Create an API key from the dashboard
3. Set the environment variable:

```bash
export BRAVE_SEARCH_API_KEY=BSAxxxxxxxxxxxx
```

**Available Tools:**
- `brave_web_search` - Search the web
- `brave_local_search` - Search for local businesses

### Slack Connector

Access Slack workspace messages and channels.

**Setup:**

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Add bot token scopes: `channels:history`, `channels:read`, `users:read`
3. Install the app to your workspace
4. Set the environment variables:

```bash
export SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx
export SLACK_TEAM_ID=T0XXXXXXXXX
```

**Available Tools:**
- `list_channels` - List channels in workspace
- `read_channel` - Read messages from a channel
- `search_messages` - Search messages

### SQLite Connector

Query SQLite databases for data analysis.

**Setup:**

1. Set the path to your SQLite database:

```bash
export SQLITE_DB_PATH=/path/to/database.db
```

**Security Note:** Consider using a read-only copy of the database for safety.

**Available Tools:**
- `query` - Execute SQL queries
- `list_tables` - List available tables
- `describe_table` - Get table schema

### Filesystem Connector

Access local filesystem for reading and managing files.

**Setup:**

```bash
export FILESYSTEM_ALLOWED_PATH=/app/uploads
```

**Security Warning:** This connector is marked as DANGEROUS. Only expose directories that are safe for AI access. Consider:
- Using read-only mounts in production
- Limiting to specific subdirectories
- Regular security audits

**Available Tools:**
- `read_file` - Read file contents
- `list_directory` - List directory contents
- `search_files` - Search for files by pattern

---

## Adding MCP Servers

### Via Admin UI (Recommended)

The easiest way to manage MCP servers is through the Admin UI:

1. Navigate to **Admin > Agents > MCP Servers**
2. You'll see pre-configured connectors for popular services (GitHub, Notion, Google Drive, etc.)
3. Click **Setup Wizard** on any connector to see:
   - Required environment variables
   - Whether each variable is configured
   - Step-by-step setup instructions
   - Links to documentation
4. After configuring environment variables, click **Activate**
5. Use **Test Connection** to verify the server is working

The health overview at the top shows real-time status of all servers:
- **Healthy**: Server is running and accessible
- **Unhealthy**: Server is active but failing
- **Needs Setup**: Missing environment variables
- **Inactive**: Server is disabled

### Via Admin API

```bash
# Create MCP server
curl -X POST "http://localhost:8000/api/v1/admin/mcp-servers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "brave-search",
    "display_name": "Brave Web Search",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
    "env_vars": {
      "BRAVE_API_KEY": "${BRAVE_SEARCH_API_KEY}"
    },
    "is_active": true
  }'
```

### Via Database Seed

Add to `backend/airbeeps/config/seed.yaml`:

```yaml
mcp_servers:
  - name: brave-search
    display_name: Brave Web Search
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-brave-search"
    env_vars:
      BRAVE_API_KEY: "${BRAVE_SEARCH_API_KEY}"
    is_active: true

  - name: filesystem
    display_name: File System
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/app/uploads" # Scoped to uploads directory
    is_active: true
```

### Testing Connection

```bash
# Test MCP server connection
curl -X POST "http://localhost:8000/api/v1/admin/mcp-servers/{id}/test" \
  -H "Authorization: Bearer $TOKEN"

# List available tools
curl -X GET "http://localhost:8000/api/v1/admin/mcp-servers/{name}/tools" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Creating Custom MCP Servers

### Python Server (FastMCP)

```python
# my_mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("My Custom Server")

@mcp.tool()
def search_database(query: str, limit: int = 10) -> str:
    """
    Search the internal database.

    Args:
        query: Search query string
        limit: Maximum results to return

    Returns:
        JSON string of search results
    """
    results = db.search(query, limit=limit)
    return json.dumps(results)

@mcp.resource("config://settings")
def get_settings() -> str:
    """Return current settings as JSON."""
    return json.dumps(settings.dict())

if __name__ == "__main__":
    mcp.run()
```

### Node.js Server

```typescript
// my-mcp-server.ts
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server(
  { name: "my-custom-server", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "search_database",
      description: "Search the internal database",
      inputSchema: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query" },
          limit: { type: "integer", default: 10 },
        },
        required: ["query"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "search_database") {
    const results = await db.search(args.query, args.limit);
    return { content: [{ type: "text", text: JSON.stringify(results) }] };
  }

  throw new Error(`Unknown tool: ${name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

### Registering Custom Server

```bash
# Register with Airbeeps
curl -X POST "http://localhost:8000/api/v1/admin/mcp-servers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-custom-server",
    "display_name": "My Custom Server",
    "command": "python",
    "args": ["/path/to/my_mcp_server.py"],
    "is_active": true
  }'
```

---

## Security Considerations

### Principle of Least Privilege

1. **Scope file access** - Only allow specific directories
2. **Validate SQL queries** - Prevent injection attacks
3. **Rate limit** - Prevent abuse
4. **Audit logging** - Track all tool usage

### Sandboxing

MCP servers should run with limited permissions:

```yaml
# docker-compose example
services:
  mcp-filesystem:
    image: mcp-servers/filesystem
    volumes:
      - ./uploads:/app/uploads:ro # Read-only mount
    security_opt:
      - no-new-privileges:true
    read_only: true
```

### Security Levels by Server

| Server       | Level     | Risks          | Mitigations        |
| ------------ | --------- | -------------- | ------------------ |
| Brave Search | SAFE      | None           | Rate limit         |
| Filesystem   | DANGEROUS | Path traversal | Scope to directory |
| SQLite       | MODERATE  | SQL injection  | Query validation   |
| GitHub       | MODERATE  | Token exposure | Scoped tokens      |

### Content Filtering

All MCP tool inputs/outputs are filtered:

```python
from airbeeps.agents.security import ContentFilter

filter = ContentFilter()

# Sanitize file paths
safe_path = filter.sanitize_path(user_path)  # Removes ../, etc.

# Validate SQL
safe_sql = filter.validate_sql(user_sql)  # Checks for dangerous patterns

# Redact PII from output
safe_output = filter.redact_pii(tool_output)
```

---

## Deployment Patterns

### Pattern 1: Sidecar Containers

Run MCP servers as sidecars to the main application:

```yaml
# docker-compose.yml
version: "3.8"

services:
  airbeeps:
    image: airbeeps/backend
    environment:
      - MCP_BRAVE_SEARCH_COMMAND=mcp-brave-search
      - MCP_BRAVE_SEARCH_HOST=mcp-brave-search
    depends_on:
      - mcp-brave-search

  mcp-brave-search:
    image: airbeeps/mcp-brave-search
    environment:
      - BRAVE_API_KEY=${BRAVE_API_KEY}
    networks:
      - mcp-network

networks:
  mcp-network:
    driver: bridge
```

### Pattern 2: Subprocess

Run MCP servers as subprocesses (default):

```yaml
# settings.yaml
mcp_servers:
  - name: brave-search
    command: npx
    args: ["-y", "@modelcontextprotocol/server-brave-search"]
    env_vars:
      BRAVE_API_KEY: "${BRAVE_SEARCH_API_KEY}"
```

### Pattern 3: Remote MCP

Connect to remote MCP servers (future):

```yaml
# settings.yaml
mcp_servers:
  - name: remote-search
    transport: sse # Server-Sent Events
    url: https://mcp.example.com/search
    api_key: "${REMOTE_MCP_KEY}"
```

### Docker Image for MCP Servers

```dockerfile
# docker/mcp-servers/Dockerfile
FROM node:20-slim

# Install common MCP servers
RUN npm install -g \
    @modelcontextprotocol/server-brave-search \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-sqlite

# Copy Python MCP servers
COPY requirements-mcp.txt /app/
RUN pip install -r /app/requirements-mcp.txt

# Entry script
COPY entrypoint.sh /app/
ENTRYPOINT ["/app/entrypoint.sh"]
```

---

## Troubleshooting

### Common Issues

#### Server Not Starting

```bash
# Check if command exists
which npx

# Run manually to see errors
npx -y @modelcontextprotocol/server-brave-search

# Check environment variables
echo $BRAVE_API_KEY
```

#### Connection Timeout

```python
# Increase timeout in config
MCP_CONNECTION_TIMEOUT=30  # seconds

# Check server health
curl -X POST "http://localhost:8000/api/v1/admin/mcp-servers/{id}/test"
```

#### Tool Not Found

```bash
# List all tools from server
curl -X GET "http://localhost:8000/api/v1/admin/mcp-servers/{name}/tools" \
  -H "Authorization: Bearer $TOKEN"

# Check server logs
docker logs mcp-brave-search
```

### Debug Mode

Enable MCP debug logging:

```bash
# Environment variable
export MCP_DEBUG=1
export AIRBEEPS_LOG_LEVEL=DEBUG

# Or in settings.yaml
logging:
  level: DEBUG
  mcp_debug: true
```

### Health Checks

```python
from airbeeps.agents.resilience import HealthRegistry

# Register MCP health check
registry = HealthRegistry.get_instance()
registry.register(
    name="mcp-brave-search",
    check_func=lambda: mcp_client.list_tools("brave-search"),
)

# Run check
result = await registry.check("mcp-brave-search")
print(result.status)  # healthy, degraded, unhealthy
```

### Circuit Breaker for MCP

```python
from airbeeps.agents.resilience import get_circuit_breaker, CircuitBreakerConfig

# Create circuit breaker for MCP server
breaker = get_circuit_breaker(
    "mcp-brave-search",
    CircuitBreakerConfig.for_mcp(),
)

# Use in tool execution
try:
    result = await breaker.call(mcp_tool.execute, query=query)
except CircuitOpenError:
    # Server is failing, use fallback
    result = await fallback_search(query)
```

---

## API Reference

### MCP Server Management

| Endpoint                                    | Method | Description        |
| ------------------------------------------- | ------ | ------------------ |
| `/api/v1/admin/mcp-servers`                 | GET    | List all servers   |
| `/api/v1/admin/mcp-servers`                 | POST   | Create server      |
| `/api/v1/admin/mcp-servers/{id}`            | GET    | Get server details |
| `/api/v1/admin/mcp-servers/{id}`            | DELETE | Delete server      |
| `/api/v1/admin/mcp-servers/{id}/test`       | POST   | Test connection    |
| `/api/v1/admin/mcp-servers/{id}/activate`   | POST   | Activate server    |
| `/api/v1/admin/mcp-servers/{id}/deactivate` | POST   | Deactivate server  |
| `/api/v1/admin/mcp-servers/{name}/tools`    | GET    | List server tools  |

### MCP Client

```python
from airbeeps.agents.mcp import MCPClient, MCPClientRegistry

# Get or create client
registry = MCPClientRegistry()
client = await registry.get_client("brave-search")

# List tools
tools = await client.list_tools()

# Call tool
result = await client.call_tool("brave_web_search", {"query": "AI news"})

# List resources
resources = await client.list_resources()

# Read resource
content = await client.read_resource("config://settings")
```

---

## Best Practices

### 1. Version Pin MCP Servers

```yaml
mcp_servers:
  - name: brave-search
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-brave-search@1.0.0" # Pin version
```

### 2. Use Environment Variables for Secrets

```yaml
env_vars:
  API_KEY: "${MY_API_KEY}" # Reference from environment
```

### 3. Set Reasonable Timeouts

```yaml
mcp_servers:
  - name: slow-server
    timeout_seconds: 60 # Increase for slow operations
```

### 4. Monitor Health

```python
# Regular health checks
@scheduler.scheduled_job("interval", minutes=1)
async def check_mcp_health():
    results = await health_registry.check_all()
    for name, health in results.items():
        if health.status == HealthStatus.UNHEALTHY:
            alert(f"MCP server {name} is unhealthy: {health.message}")
```

### 5. Use Circuit Breakers

```python
# Prevent cascading failures
@circuit_breaker("mcp-database", config=CircuitBreakerConfig.for_mcp())
async def query_database(query: str):
    return await mcp_client.call_tool("query", {"sql": query})
```

---

## Further Reading

- [MCP Specification](https://modelcontextprotocol.io/docs)
- [Agent Development Guide](AGENT_DEVELOPMENT.md)
- [Security Best Practices](configuration.md#security)
