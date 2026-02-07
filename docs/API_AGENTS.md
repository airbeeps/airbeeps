# Agent API Reference

This document covers all API endpoints related to agents, tools, MCP servers, memory, tracing, and multi-agent functionality.

## Table of Contents

- [Health & Resilience](#health--resilience)
- [MCP Server Management](#mcp-server-management)
- [Tool Management](#tool-management)
- [Memory Management](#memory-management)
- [Tracing & Analytics](#tracing--analytics)
- [Multi-Agent](#multi-agent)

---

## Health & Resilience

Endpoints for monitoring service health and resilience patterns.

### Overall Health Check

```
GET /api/v1/health
```

Returns aggregated health status of all registered services.

**Response:**

```json
{
  "status": "healthy",
  "services": {
    "database": {
      "status": "healthy",
      "message": "OK",
      "latency_ms": 5.2
    },
    "mcp-brave-search": {
      "status": "healthy",
      "message": "OK",
      "latency_ms": 120.5
    }
  }
}
```

### Kubernetes Probes

```
GET /api/v1/health/ready
```

Readiness probe - returns 200 if service is ready, 503 if not.

```
GET /api/v1/health/live
```

Liveness probe - returns 200 if service is alive.

### Service Health

```
GET /api/v1/health/services/{service_name}
```

Health check for a specific service.

### Circuit Breakers

```
GET /api/v1/health/circuits
```

List all circuit breakers and their states.

**Response:**

```json
{
  "circuits": {
    "mcp-brave-search": {
      "name": "mcp-brave-search",
      "state": "CLOSED",
      "failure_count": 0,
      "time_until_recovery": null
    }
  },
  "open_circuits": []
}
```

```
GET /api/v1/health/circuits/{circuit_name}
```

Get specific circuit breaker status.

```
POST /api/v1/health/circuits/{circuit_name}/reset
```

Manually reset a circuit breaker to closed state.

### Prometheus Metrics

```
GET /metrics
```

Prometheus metrics endpoint (if prometheus_client is installed).

---

## MCP Server Management

Endpoints for managing MCP (Model Context Protocol) servers.

### List MCP Servers

```
GET /api/v1/admin/mcp-servers
```

List all registered MCP servers.

**Response:**

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "brave-search",
      "display_name": "Brave Web Search",
      "is_active": true,
      "last_health_check": "2026-01-30T10:00:00Z"
    }
  ],
  "total": 1
}
```

### Create MCP Server

```
POST /api/v1/admin/mcp-servers
```

**Request:**

```json
{
  "name": "brave-search",
  "display_name": "Brave Web Search",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env_vars": {
    "BRAVE_API_KEY": "${BRAVE_SEARCH_API_KEY}"
  },
  "is_active": true
}
```

### Get MCP Server

```
GET /api/v1/admin/mcp-servers/{id}
```

### Delete MCP Server

```
DELETE /api/v1/admin/mcp-servers/{id}
```

### Test MCP Server Connection

```
POST /api/v1/admin/mcp-servers/{id}/test
```

Test connection to an MCP server.

**Response:**

```json
{
  "success": true,
  "message": "Connection successful",
  "tools_available": 5
}
```

### Activate/Deactivate MCP Server

```
POST /api/v1/admin/mcp-servers/{id}/activate
POST /api/v1/admin/mcp-servers/{id}/deactivate
```

### List Server Tools

```
GET /api/v1/admin/mcp-servers/{name}/tools
```

List tools available from an MCP server.

**Response:**

```json
{
  "tools": [
    {
      "name": "brave_web_search",
      "description": "Search the web using Brave Search",
      "inputSchema": {...}
    }
  ]
}
```

---

## Tool Management

Endpoints for managing agent tools.

### List All Tools

```
GET /api/v1/admin/tools
```

List all available tools (local + MCP combined).

**Response:**

```json
{
  "tools": [
    {
      "name": "web_search",
      "description": "Search the web",
      "security_level": "SAFE",
      "source": "local"
    },
    {
      "name": "brave_web_search",
      "description": "Brave Search",
      "security_level": "SAFE",
      "source": "mcp:brave-search"
    }
  ]
}
```

### Get Tool Permissions

```
GET /api/v1/admin/tools/{tool_name}/permissions
```

View permission requirements for a tool.

**Response:**

```json
{
  "tool_name": "execute_python",
  "security_level": "DANGEROUS",
  "required_roles": ["admin", "developer"],
  "rate_limit": {
    "calls_per_hour": 100
  }
}
```

### Test Tool Execution

```
POST /api/v1/admin/tools/{tool_name}/test
```

Test execute a tool with sample input.

**Request:**

```json
{
  "input": {
    "query": "test query"
  }
}
```

---

## Memory Management

Endpoints for managing agent memory (GDPR-compliant).

### User Endpoints (Self-Service)

#### Get Consent Status

```
GET /api/v1/memory/consent
```

**Response:**

```json
{
  "consent_given": true,
  "consent_date": "2026-01-15T10:00:00Z",
  "allowed_types": ["CONVERSATION", "PREFERENCE"]
}
```

#### Grant Consent

```
POST /api/v1/memory/consent
```

**Request:**

```json
{
  "allowed_types": ["CONVERSATION", "PREFERENCE", "EPISODIC"]
}
```

#### Revoke Consent

```
DELETE /api/v1/memory/consent
```

**Query params:**

- `delete_existing=true` - Also delete all existing memories

#### Get Memory Statistics

```
GET /api/v1/memory/stats
```

**Response:**

```json
{
  "total_memories": 42,
  "by_type": {
    "CONVERSATION": 20,
    "PREFERENCE": 15,
    "EPISODIC": 7
  },
  "oldest_memory": "2026-01-01T00:00:00Z"
}
```

#### Export All Memories (GDPR)

```
GET /api/v1/memory/export
```

Download all memories as JSON (data portability).

#### Delete All Memories (GDPR)

```
DELETE /api/v1/memory/all
```

Right to be forgotten - deletes all memories.

### Admin Endpoints

#### Store Memory

```
POST /api/v1/admin/memory/store
```

Store a memory (bypasses consent check).

#### Delete User Memories

```
DELETE /api/v1/admin/memory/users/{user_id}/all
```

#### Prune Expired Memories

```
POST /api/v1/admin/memory/prune/expired
```

#### Retention Policies

```
GET /api/v1/admin/memory/policies
POST /api/v1/admin/memory/policies
```

---

## Tracing & Analytics

Endpoints for viewing agent traces and analytics.

### List Traces

```
GET /api/v1/admin/traces
```

**Query params:**

- `user_id` - Filter by user
- `assistant_id` - Filter by assistant
- `conversation_id` - Filter by conversation
- `start_date` / `end_date` - Date range
- `span_type` - Filter by type (agent, tool, llm)
- `success` - Filter by success/failure
- `offset` / `limit` - Pagination

**Response:**

```json
{
  "items": [
    {
      "id": "uuid",
      "trace_id": "otel-trace-id",
      "span_name": "agent_execution",
      "span_type": "agent",
      "start_time": "2026-01-30T10:00:00Z",
      "latency_ms": 5000,
      "success": true
    }
  ],
  "total": 100
}
```

### Get Trace Detail

```
GET /api/v1/admin/traces/{id}
```

### Get Trace Statistics

```
GET /api/v1/admin/traces/stats
```

**Response:**

```json
{
  "total_traces": 1000,
  "success_rate": 0.95,
  "avg_latency_ms": 3500,
  "total_cost_usd": 15.5,
  "by_span_type": {
    "agent": 200,
    "tool": 500,
    "llm": 300
  }
}
```

### Tool Usage Analytics

```
GET /api/v1/admin/traces/analytics/tools
```

**Response:**

```json
{
  "by_tool": {
    "web_search": {
      "total_calls": 500,
      "success_rate": 0.98,
      "avg_latency_ms": 800
    },
    "knowledge_base_query": {
      "total_calls": 300,
      "success_rate": 0.99,
      "avg_latency_ms": 200
    }
  }
}
```

### Cost Analytics

```
GET /api/v1/admin/traces/analytics/cost
```

**Query params:**

- `start_date` / `end_date` - Date range
- `group_by` - day, week, month

### Delete Old Traces

```
DELETE /api/v1/admin/traces/old
```

Delete traces older than retention period.

---

## Multi-Agent

Endpoints for multi-agent collaboration.

### List Specialist Types

```
GET /api/v1/multiagent/specialists
```

**Response:**

```json
{
  "specialists": [
    {
      "type": "RESEARCH",
      "description": "Web search and document research",
      "tools": ["web_search", "knowledge_base_query"]
    },
    {
      "type": "CODE",
      "description": "Code generation and execution",
      "tools": ["execute_python", "file_operations"]
    }
  ]
}
```

### Get Specialist Config

```
GET /api/v1/multiagent/specialists/{type}
```

### Classify Request

```
POST /api/v1/multiagent/classify
```

Classify a user request to determine appropriate specialist.

**Request:**

```json
{
  "user_input": "Search for Python tutorials and write a script"
}
```

**Response:**

```json
{
  "specialist_type": "RESEARCH",
  "confidence": 0.85,
  "reasoning": "Request involves web search",
  "method": "keyword"
}
```

### List Collaboration Logs (Admin)

```
GET /api/v1/admin/multiagent/logs
```

**Query params:**

- `user_id` - Filter by user
- `status` - Filter by status
- `offset` / `limit` - Pagination

### Get Collaboration Log Detail

```
GET /api/v1/admin/multiagent/logs/{id}
```

### Get Collaboration Statistics

```
GET /api/v1/admin/multiagent/stats
```

**Response:**

```json
{
  "total_collaborations": 150,
  "successful": 140,
  "failed": 10,
  "total_handoffs": 200,
  "total_cost_usd": 45.0,
  "avg_duration_ms": 8000,
  "most_used_specialists": {
    "RESEARCH": 80,
    "CODE": 50,
    "DATA": 20
  },
  "common_handoff_patterns": [
    ["GENERAL", "RESEARCH"],
    ["RESEARCH", "CODE"]
  ]
}
```

### Delete Collaboration Log

```
DELETE /api/v1/admin/multiagent/logs/{id}
```

### Delete Old Logs

```
DELETE /api/v1/admin/multiagent/logs/old
```

---

## Error Responses

All endpoints may return standard error responses:

### 400 Bad Request

```json
{
  "detail": "Invalid request format"
}
```

### 401 Unauthorized

```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden

```json
{
  "detail": "Permission denied"
}
```

### 404 Not Found

```json
{
  "detail": "Resource not found"
}
```

### 429 Too Many Requests

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error"
}
```

### 503 Service Unavailable

```json
{
  "detail": "Service temporarily unavailable",
  "circuit_open": true
}
```
