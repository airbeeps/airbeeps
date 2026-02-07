# Agent Development Guide

This guide covers how to develop, configure, and extend agents in Airbeeps.

## Table of Contents

- [Overview](#overview)
- [Agent Architecture](#agent-architecture)
- [Creating Custom Tools](#creating-custom-tools)
- [Configuring Agents](#configuring-agents)
- [Security Considerations](#security-considerations)
- [Debugging Techniques](#debugging-techniques)
- [Best Practices](#best-practices)

---

## Overview

Airbeeps uses a LangGraph-based agent architecture that supports:

- **Multi-step reasoning** with planning, execution, and reflection
- **Budget controls** for tokens, iterations, and costs
- **Parallel tool execution** with retry logic and circuit breakers
- **Memory systems** for long-term context
- **Multi-agent collaboration** with specialist routing

### Key Components

| Component                | Description                       |
| ------------------------ | --------------------------------- |
| `AgentExecutionEngine`   | Basic ReAct loop executor         |
| `LangGraphAgentEngine`   | Advanced LangGraph-based executor |
| `MultiAgentOrchestrator` | Coordinates specialist agents     |
| `AgentTool`              | Base class for all tools          |
| `MemoryService`          | Long-term memory with encryption  |

---

## Agent Architecture

### Execution Flow

```
User Input
    │
    ▼
┌─────────────────┐
│  Budget Checker │ ◄─── Check token/cost limits
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Planner      │ ◄─── Decompose task, recall memories
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Executor     │ ◄─── Execute tools (parallel)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Reflector     │ ◄─── Evaluate quality, decide next step
└────────┬────────┘
         │
    ┌────┴────┐
    │ Quality │
    │   OK?   │
    └────┬────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  Loop    Responder
  Back    (Generate)
```

### State Management

The agent state is managed through `AgentState`:

```python
from airbeeps.agents.graph.state import AgentState

state = AgentState(
    user_input="Search for AI news",
    messages=[],
    iterations=0,
    token_budget=8000,
    max_iterations=10,
    cost_limit_usd=0.50,
)
```

---

## Creating Custom Tools

### Basic Tool Structure

All tools must inherit from `AgentTool`:

```python
from airbeeps.agents.tools.base import AgentTool, AgentToolConfig

class MyCustomTool(AgentTool):
    """Description of what this tool does."""

    @property
    def name(self) -> str:
        return "my_custom_tool"

    @property
    def description(self) -> str:
        return "A detailed description of the tool's purpose and usage."

    @property
    def security_level(self) -> str:
        """SAFE, MODERATE, or DANGEROUS"""
        return "SAFE"

    def get_input_schema(self) -> dict:
        """JSON Schema for tool inputs."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": ["query"]
        }

    async def execute(self, query: str, limit: int = 10) -> str:
        """Execute the tool and return results."""
        # Your implementation here
        results = await self._do_search(query, limit)
        return f"Found {len(results)} results:\n{results}"
```

### Registering Tools

Register tools using the registry:

```python
from airbeeps.agents.tools.registry import tool_registry

# Decorator registration
@tool_registry.register
class MyTool(AgentTool):
    ...

# Manual registration
tool_registry.register_tool(MyTool)
```

### Security Levels

| Level       | Description                         | Examples                   |
| ----------- | ----------------------------------- | -------------------------- |
| `SAFE`      | No side effects, read-only          | Web search, KB query       |
| `MODERATE`  | Limited side effects, scoped access | File read, data analysis   |
| `DANGEROUS` | Can modify system, requires sandbox | Code execution, file write |

### Tool Configuration

Tools can accept configuration via `AgentToolConfig`:

```python
class MyTool(AgentTool):
    def __init__(self, config: AgentToolConfig | None = None, session=None):
        super().__init__(config)
        self.session = session

        # Access parameters from config
        self.api_key = self.config.parameters.get("api_key")
        self.base_url = self.config.parameters.get("base_url")
```

---

## Configuring Agents

### Assistant Model Configuration

Configure agent behavior through the `Assistant` model:

```python
assistant = Assistant(
    name="Research Assistant",
    system_prompt="You are a research specialist...",

    # Tool configuration
    agent_tools_enabled=True,
    agent_max_iterations=10,

    # Budget controls
    agent_token_budget=8000,
    agent_max_tool_calls=20,
    agent_cost_limit_usd=0.50,

    # Behavior
    agent_enable_planning=True,
    agent_enable_reflection=True,
    agent_reflection_threshold=7.0,

    # Agentic RAG
    agent_rag_mode="query_planning",  # standard, query_planning, self_rag, multi_hop
    agent_enable_query_planning=True,
    agent_enable_self_rag=True,
    agent_self_rag_min_confidence=70,

    # Memory
    enable_memory=True,

    # Specialist (for multi-agent)
    specialist_type="RESEARCH",
    can_collaborate=True,
)
```

### Using Different Executors

```python
from airbeeps.agents import get_agent_executor

# Use LangGraph executor (recommended)
executor = await get_agent_executor(
    assistant=assistant,
    session=db_session,
    user=current_user,
    use_langgraph=True,
)

# Execute
result = await executor.execute(
    user_input="Search for recent AI developments",
    chat_history=history,
)
```

### Streaming Execution

```python
async for event in executor.stream_execute(user_input, chat_history):
    match event["type"]:
        case "planning":
            print(f"Planning: {event['data']['plan']}")
        case "agent_action":
            print(f"Using tool: {event['data']['tool']}")
        case "tool_result":
            print(f"Tool result: {event['data']['result'][:100]}")
        case "content_chunk":
            print(event["data"]["content"], end="")
        case "budget_warning":
            print(f"Warning: {event['data']['message']}")
```

---

## Security Considerations

### Input Validation

All tool inputs are validated through multiple layers:

1. **JSON Schema validation** - Type checking
2. **Content filtering** - Sanitization of paths, SQL, etc.
3. **Permission checks** - Role-based access control

```python
from airbeeps.agents.security import ContentFilter, ToolPermissionChecker

# Check permissions before execution
if not await permission_checker.can_use_tool(user, tool.name):
    raise PermissionError("Not authorized")

# Filter inputs
filtered_input = await content_filter.filter_input(tool.name, raw_input)

# Execute
result = await tool.execute(**filtered_input)

# Filter outputs
filtered_output = await content_filter.filter_output(tool.name, result)
```

### Code Execution Sandbox

Code execution always runs in a sandbox:

```python
from airbeeps.agents.security.sandbox import CodeSandbox

sandbox = CodeSandbox(
    max_memory_mb=256,
    max_cpu_percent=50,
    timeout_seconds=30,
    allowed_imports=["math", "json", "datetime", "pandas"],
)

result = await sandbox.execute(code)
```

### File Operation Scoping

File operations are scoped to specific directories:

```python
class FileOperationsTool(AgentTool):
    async def execute(self, operation: str, path: str, content: str = None):
        # Validate path is within allowed directory
        if not self._is_path_allowed(path):
            raise PermissionError("Path outside allowed directory")

        # Sanitize (no .., no symlinks)
        safe_path = self._sanitize_path(path)
        ...
```

---

## Debugging Techniques

### Enable Tracing

Configure tracing to capture detailed execution logs:

```bash
# Environment variables
AIRBEEPS_TRACING_ENABLED=true
AIRBEEPS_TRACING_BACKEND=local  # or otlp, jaeger
AIRBEEPS_TRACING_REDACT_PII=true
```

### View Traces

Access traces via the admin API:

```bash
# List traces
curl -X GET "http://localhost:8000/api/v1/admin/traces" \
  -H "Authorization: Bearer $TOKEN"

# Get trace detail
curl -X GET "http://localhost:8000/api/v1/admin/traces/{trace_id}" \
  -H "Authorization: Bearer $TOKEN"
```

### Debug Mode in Chat

Enable developer mode for inline debugging:

```python
# In chat component, add debug=True
result = await executor.execute(
    user_input=input,
    debug=True,  # Returns detailed trace info
)
```

### Common Issues

| Issue             | Cause                   | Solution                              |
| ----------------- | ----------------------- | ------------------------------------- |
| Tool not found    | Not registered          | Check `tool_registry.list_tools()`    |
| Permission denied | User role insufficient  | Check user roles and tool permissions |
| Timeout           | Tool execution too slow | Increase timeout or optimize tool     |
| Budget exceeded   | Too many iterations     | Increase limits or simplify prompt    |

---

## Best Practices

### Prompt Engineering

1. **Be specific** - Clear instructions reduce iterations
2. **Include examples** - Show expected tool usage
3. **Set constraints** - Define what the agent should NOT do

```python
system_prompt = """
You are a research assistant. You help users find information.

TOOLS:
- web_search: Search the web for current information
- knowledge_base_query: Search internal documents

GUIDELINES:
- Always cite sources
- If unsure, ask for clarification
- Limit searches to 3 per request
- Never fabricate information

EXAMPLE:
User: What are the latest AI developments?
Assistant: I'll search for recent AI news.
[Uses web_search tool]
Based on my search, here are the key developments...
"""
```

### Tool Design

1. **Single responsibility** - One tool, one purpose
2. **Clear descriptions** - Help LLM understand when to use
3. **Robust error handling** - Return helpful error messages
4. **Idempotency** - Safe to retry

```python
class GoodTool(AgentTool):
    @property
    def description(self) -> str:
        return """
        Search the knowledge base for documents matching a query.

        Use this when:
        - User asks about internal policies
        - User needs company-specific information
        - User references documents or files

        Do NOT use when:
        - User needs current/external information (use web_search)
        - User asks general knowledge questions
        """
```

### Cost Optimization

1. **Set appropriate budgets** - Prevent runaway costs
2. **Use state compression** - Summarize long conversations
3. **Cache tool results** - Avoid redundant calls
4. **Choose right model** - Use cheaper models for simple tasks

```python
# Budget configuration
assistant.agent_token_budget = 8000  # Per conversation
assistant.agent_cost_limit_usd = 0.50  # Hard stop
assistant.agent_max_iterations = 10  # Prevent loops
```

### Error Handling

```python
from airbeeps.agents.resilience import (
    execute_with_retry,
    CircuitBreaker,
    RetryConfig,
)

# Use retry for transient failures
result = await execute_with_retry(
    tool.execute,
    query=query,
    config=RetryConfig(max_attempts=3),
)

# Use circuit breaker for external services
breaker = CircuitBreaker("external_api")
result = await breaker.call(external_api.search, query)
```

---

## API Reference

### Agent Executors

| Class                    | Description                   |
| ------------------------ | ----------------------------- |
| `AgentExecutionEngine`   | Basic ReAct executor          |
| `LangGraphAgentEngine`   | Advanced graph-based executor |
| `MultiAgentOrchestrator` | Multi-agent coordinator       |

### Tools

| Tool                 | Security  | Description              |
| -------------------- | --------- | ------------------------ |
| `KnowledgeBaseTool`  | SAFE      | Query internal documents |
| `WebSearchTool`      | SAFE      | Search the web           |
| `CodeExecutorTool`   | DANGEROUS | Execute Python code      |
| `FileOperationsTool` | MODERATE  | Read/write files         |
| `DataAnalysisTool`   | SAFE      | Analyze CSV/Excel data   |

### Configuration

| Setting                   | Type  | Default | Description          |
| ------------------------- | ----- | ------- | -------------------- |
| `agent_max_iterations`    | int   | 10      | Max reasoning loops  |
| `agent_token_budget`      | int   | 8000    | Token limit per turn |
| `agent_cost_limit_usd`    | float | 0.50    | Cost limit per turn  |
| `agent_enable_planning`   | bool  | True    | Enable task planning |
| `agent_enable_reflection` | bool  | True    | Enable self-critique |

---

## Examples

### Research Assistant

```python
# See docs/examples/research_assistant.yaml
assistant = Assistant(
    name="Research Assistant",
    specialist_type="RESEARCH",
    agent_tools_enabled=True,
    agent_rag_mode="query_planning",
)

# Attach tools
assistant.agent_tools = ["web_search", "knowledge_base_query"]
```

### Code Assistant

```python
# See docs/examples/code_assistant.yaml
assistant = Assistant(
    name="Code Assistant",
    specialist_type="CODE",
    agent_tools_enabled=True,
)

# Attach tools
assistant.agent_tools = ["execute_python", "file_operations"]
```

### Data Analyst

```python
# See docs/examples/data_analyst.yaml
assistant = Assistant(
    name="Data Analyst",
    specialist_type="DATA",
    agent_tools_enabled=True,
)

# Attach tools
assistant.agent_tools = ["analyze_data", "list_tabular_documents"]
```

---

## Further Reading

- [MCP Integration Guide](MCP_INTEGRATION.md) - Adding MCP servers
- [Configuration Guide](configuration.md) - Full configuration options
- [Admin Features](ADMIN_FEATURES.md) - Admin panel usage
