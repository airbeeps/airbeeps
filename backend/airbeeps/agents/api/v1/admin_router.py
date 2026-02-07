"""
Agent API v1 - Admin routes

Provides endpoints for:
- MCP server management (CRUD)
- Tool listing and testing
- Health checks
- Permission management
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from airbeeps.agents.mcp.registry import mcp_registry
from airbeeps.agents.schemas import (
    MCPServerConfigCreate,
    MCPServerConfigResponse,
    MCPServerToolsResponse,
    MCPToolInfo,
)
from airbeeps.agents.security.permissions import PermissionChecker, ToolSecurityLevel
from airbeeps.agents.service import MCPServerService
from airbeeps.agents.tools.registry import tool_registry
from airbeeps.auth import current_superuser
from airbeeps.database import get_async_session
from airbeeps.users.models import User

router = APIRouter(prefix="/mcp-servers")
tools_router = APIRouter(prefix="/tools")


# Additional schemas for new endpoints
class MCPServerTestRequest(BaseModel):
    """Request to test MCP server connection"""

    timeout_seconds: int = 30


class MCPServerTestResponse(BaseModel):
    """Response from MCP server test"""

    success: bool
    message: str
    tools_count: int | None = None
    latency_ms: int | None = None


class MCPServerActivateResponse(BaseModel):
    """Response from activating MCP server"""

    success: bool
    message: str
    is_active: bool


class EnvVarStatus(BaseModel):
    """Status of a single environment variable"""

    name: str
    description: str | None = None
    docs_url: str | None = None
    is_set: bool
    value_preview: str | None = None  # First few chars if set


class MCPServerEnvCheckResponse(BaseModel):
    """Response from MCP server env var check"""

    server_name: str
    all_vars_set: bool
    env_vars: list[EnvVarStatus]
    setup_instructions: str | None = None


class MCPServerHealthResponse(BaseModel):
    """Health status response for MCP server"""

    server_id: str
    server_name: str
    is_active: bool
    is_healthy: bool
    status: str  # "healthy", "unhealthy", "unconfigured", "inactive"
    message: str
    last_check_ms: int | None = None
    tools_count: int | None = None


class ToolInfoResponse(BaseModel):
    """Tool information response"""

    name: str
    description: str
    security_level: str
    source: str  # "local" or MCP server name
    input_schema: dict[str, Any] = {}


class ToolPermissionResponse(BaseModel):
    """Tool permission information"""

    tool_name: str
    security_level: str
    allowed_roles: list[str]
    requires_approval: bool
    max_calls_per_hour: int
    max_calls_per_day: int


class AllToolsResponse(BaseModel):
    """Response with all available tools"""

    local_tools: list[ToolInfoResponse]
    mcp_tools: list[ToolInfoResponse]
    total_count: int


@router.post(
    "", response_model=MCPServerConfigResponse, status_code=status.HTTP_201_CREATED
)
async def create_mcp_server(
    server_data: MCPServerConfigCreate,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Create MCP server configuration (Admin only)"""
    service = MCPServerService(session)
    server = await service.create_mcp_server(server_data.model_dump())
    return MCPServerConfigResponse.model_validate(server)


@router.get("", response_model=list[MCPServerConfigResponse])
async def list_mcp_servers(
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """List all MCP server configurations (Admin only)"""
    service = MCPServerService(session)
    servers = await service.list_mcp_servers()
    return [MCPServerConfigResponse.model_validate(s) for s in servers]


@router.get("/{server_id}", response_model=MCPServerConfigResponse)
async def get_mcp_server(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Get MCP server configuration (Admin only)"""
    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    return MCPServerConfigResponse.model_validate(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete MCP server configuration (Admin only)"""
    service = MCPServerService(session)
    success = await service.delete_mcp_server(server_id)

    if not success:
        raise HTTPException(status_code=404, detail="MCP server not found")


@router.get("/{server_name}/tools", response_model=MCPServerToolsResponse)
async def list_mcp_server_tools(
    server_name: str, current_user: User = Depends(current_superuser)
):
    """List tools available from MCP server (Admin only)"""
    if not mcp_registry.is_registered(server_name):
        raise HTTPException(status_code=404, detail="MCP server not registered")

    try:
        tools = await mcp_registry.list_all_tools(server_name)
        tool_infos = [
            MCPToolInfo(
                name=tool["name"],
                description=tool.get("description", ""),
                inputSchema=tool.get("inputSchema", {}),
            )
            for tool in tools
        ]

        return MCPServerToolsResponse(server_name=server_name, tools=tool_infos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{server_id}/test", response_model=MCPServerTestResponse)
async def test_mcp_server(
    server_id: uuid.UUID,
    request: MCPServerTestRequest = MCPServerTestRequest(),
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Test MCP server connection (Admin only)"""
    import time

    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    start_time = time.time()

    try:
        # Try to register and connect
        if not mcp_registry.is_registered(server.name):
            await mcp_registry.register_server(server)

        # Get client and list tools (tests connectivity)
        client = await mcp_registry.get_server(server.name)
        tools = await client.list_tools()

        latency_ms = int((time.time() - start_time) * 1000)

        return MCPServerTestResponse(
            success=True,
            message=f"Successfully connected to {server.name}",
            tools_count=len(tools),
            latency_ms=latency_ms,
        )

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return MCPServerTestResponse(
            success=False,
            message=f"Connection failed: {e!s}",
            tools_count=None,
            latency_ms=latency_ms,
        )


@router.post("/{server_id}/activate", response_model=MCPServerActivateResponse)
async def activate_mcp_server(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Activate an MCP server (Admin only)"""
    from sqlalchemy import update

    from airbeeps.agents.models import MCPServerConfig

    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # Update is_active
    await session.execute(
        update(MCPServerConfig)
        .where(MCPServerConfig.id == server_id)
        .values(is_active=True)
    )
    await session.commit()

    # Register with MCP registry
    try:
        if not mcp_registry.is_registered(server.name):
            server.is_active = True
            await mcp_registry.register_server(server)
    except Exception as e:
        return MCPServerActivateResponse(
            success=False,
            message=f"Activated but failed to register: {e!s}",
            is_active=True,
        )

    return MCPServerActivateResponse(
        success=True,
        message=f"Server {server.name} activated",
        is_active=True,
    )


@router.post("/{server_id}/deactivate", response_model=MCPServerActivateResponse)
async def deactivate_mcp_server(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Deactivate an MCP server (Admin only)"""
    from sqlalchemy import update

    from airbeeps.agents.models import MCPServerConfig

    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # Unregister from MCP registry
    if mcp_registry.is_registered(server.name):
        await mcp_registry.unregister_server(server.name)

    # Update is_active
    await session.execute(
        update(MCPServerConfig)
        .where(MCPServerConfig.id == server_id)
        .values(is_active=False)
    )
    await session.commit()

    return MCPServerActivateResponse(
        success=True,
        message=f"Server {server.name} deactivated",
        is_active=False,
    )


@router.get("/{server_id}/env-check", response_model=MCPServerEnvCheckResponse)
async def check_mcp_server_env_vars(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Check if required environment variables are set for MCP server (Admin only)"""
    import os
    import re

    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    env_vars: list[EnvVarStatus] = []
    all_vars_set = True

    # Get required env vars from extra_data
    extra_data = server.extra_data or {}
    required_vars = extra_data.get("required_env_vars", [])

    # Also check connection_config.env for ${VAR_NAME} patterns
    connection_config = server.connection_config or {}
    env_config = connection_config.get("env", {})

    # Extract variable names from ${VAR_NAME} patterns
    var_pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")

    discovered_vars = set()
    for value in env_config.values():
        if isinstance(value, str):
            matches = var_pattern.findall(value)
            discovered_vars.update(matches)

    # Also check args for ${VAR_NAME} patterns
    args = connection_config.get("args", [])
    for arg in args:
        if isinstance(arg, str):
            matches = var_pattern.findall(arg)
            discovered_vars.update(matches)

    # Build env var status from required_vars
    seen_vars = set()
    for var_def in required_vars:
        var_name = var_def.get("name", "")
        if not var_name:
            continue
        seen_vars.add(var_name)

        env_value = os.environ.get(var_name)
        is_set = env_value is not None and env_value.strip() != ""

        # Preview: show first 4 chars + *** if set
        value_preview = None
        if is_set and env_value:
            if len(env_value) > 4:
                value_preview = env_value[:4] + "***"
            else:
                value_preview = "***"

        if not is_set:
            all_vars_set = False

        env_vars.append(
            EnvVarStatus(
                name=var_name,
                description=var_def.get("description"),
                docs_url=var_def.get("docs_url"),
                is_set=is_set,
                value_preview=value_preview,
            )
        )

    # Add any discovered vars not in required_vars
    for var_name in discovered_vars:
        if var_name in seen_vars:
            continue

        env_value = os.environ.get(var_name)
        is_set = env_value is not None and env_value.strip() != ""

        value_preview = None
        if is_set and env_value:
            if len(env_value) > 4:
                value_preview = env_value[:4] + "***"
            else:
                value_preview = "***"

        if not is_set:
            all_vars_set = False

        env_vars.append(
            EnvVarStatus(
                name=var_name,
                description=None,
                docs_url=None,
                is_set=is_set,
                value_preview=value_preview,
            )
        )

    return MCPServerEnvCheckResponse(
        server_name=server.name,
        all_vars_set=all_vars_set,
        env_vars=env_vars,
        setup_instructions=extra_data.get("setup_instructions"),
    )


@router.get("/{server_id}/health", response_model=MCPServerHealthResponse)
async def get_mcp_server_health(
    server_id: uuid.UUID,
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Get health status of MCP server (Admin only)"""
    import time

    service = MCPServerService(session)
    server = await service.get_mcp_server(server_id)

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # Check if server is active
    if not server.is_active:
        return MCPServerHealthResponse(
            server_id=str(server.id),
            server_name=server.name,
            is_active=False,
            is_healthy=False,
            status="inactive",
            message="Server is not activated",
            last_check_ms=None,
            tools_count=None,
        )

    # Try to check health
    start_time = time.time()

    try:
        # Check if registered
        if not mcp_registry.is_registered(server.name):
            await mcp_registry.register_server(server)

        # Get client and list tools
        client = await mcp_registry.get_server(server.name)
        tools = await client.list_tools()

        latency_ms = int((time.time() - start_time) * 1000)

        return MCPServerHealthResponse(
            server_id=str(server.id),
            server_name=server.name,
            is_active=True,
            is_healthy=True,
            status="healthy",
            message=f"Connected successfully with {len(tools)} tools",
            last_check_ms=latency_ms,
            tools_count=len(tools),
        )

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)

        # Check for common error patterns
        status = "unhealthy"
        if "not found" in error_msg.lower() or "command failed" in error_msg.lower():
            status = "unconfigured"
            message = "Server command not found. Ensure Node.js/npx is installed."
        elif "timeout" in error_msg.lower():
            message = "Connection timed out"
        elif "token" in error_msg.lower() or "auth" in error_msg.lower():
            message = "Authentication failed. Check your API credentials."
        else:
            message = f"Connection failed: {error_msg[:100]}"

        return MCPServerHealthResponse(
            server_id=str(server.id),
            server_name=server.name,
            is_active=True,
            is_healthy=False,
            status=status,
            message=message,
            last_check_ms=latency_ms,
            tools_count=None,
        )


@router.get("/health/all", response_model=list[MCPServerHealthResponse])
async def get_all_mcp_servers_health(
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Get health status of all MCP servers (Admin only)"""
    import asyncio

    service = MCPServerService(session)
    servers = await service.list_mcp_servers()

    # Check health of each server concurrently
    async def check_server_health(server):
        try:
            # Create a new session for each concurrent check
            return await get_mcp_server_health(
                server_id=server.id,
                current_user=current_user,
                session=session,
            )
        except Exception as e:
            return MCPServerHealthResponse(
                server_id=str(server.id),
                server_name=server.name,
                is_active=server.is_active,
                is_healthy=False,
                status="error",
                message=str(e)[:100],
                last_check_ms=None,
                tools_count=None,
            )

    # Run health checks concurrently with timeout
    tasks = [check_server_health(s) for s in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    health_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            server = servers[i]
            health_results.append(
                MCPServerHealthResponse(
                    server_id=str(server.id),
                    server_name=server.name,
                    is_active=server.is_active,
                    is_healthy=False,
                    status="error",
                    message=str(result)[:100],
                    last_check_ms=None,
                    tools_count=None,
                )
            )
        else:
            health_results.append(result)

    return health_results


# Tools router endpoints


@tools_router.get("", response_model=AllToolsResponse)
async def list_all_tools(
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """List all available tools (local + MCP) (Admin only)"""
    local_tools = []
    mcp_tools = []

    # Get local tools
    for tool_name in tool_registry.list_tools():
        try:
            tool_info = tool_registry.get_tool_info(tool_name)
            tool = tool_registry.get_tool(tool_name)

            security_level = "moderate"
            input_schema = {}

            if hasattr(tool, "security_level"):
                security_level = tool.security_level.value
            if hasattr(tool, "get_input_schema"):
                input_schema = tool.get_input_schema()

            local_tools.append(
                ToolInfoResponse(
                    name=tool_info["name"],
                    description=tool_info["description"],
                    security_level=security_level,
                    source="local",
                    input_schema=input_schema,
                )
            )
        except Exception:
            continue

    # Get MCP tools from registered servers
    for server_name in mcp_registry.list_registered_servers():
        try:
            tools = await mcp_registry.list_all_tools(server_name)
            for tool in tools:
                mcp_tools.append(
                    ToolInfoResponse(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        security_level="moderate",  # MCP tools default to moderate
                        source=server_name,
                        input_schema=tool.get("inputSchema", {}),
                    )
                )
        except Exception:
            continue

    return AllToolsResponse(
        local_tools=local_tools,
        mcp_tools=mcp_tools,
        total_count=len(local_tools) + len(mcp_tools),
    )


@tools_router.get("/{tool_name}/permissions", response_model=ToolPermissionResponse)
async def get_tool_permissions(
    tool_name: str,
    current_user: User = Depends(current_superuser),
):
    """Get permission requirements for a tool (Admin only)"""
    permission_checker = PermissionChecker()
    permission = permission_checker.get_tool_permission(tool_name)

    return ToolPermissionResponse(
        tool_name=permission.tool_name,
        security_level=permission.security_level.value,
        allowed_roles=[r.value for r in permission.allowed_roles],
        requires_approval=permission.requires_approval,
        max_calls_per_hour=permission.max_calls_per_hour,
        max_calls_per_day=permission.max_calls_per_day,
    )


@tools_router.post("/{tool_name}/test")
async def test_tool_execution(
    tool_name: str,
    tool_input: dict[str, Any],
    current_user: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Test execute a tool with given input (Admin only)"""
    import time

    from airbeeps.agents.security import ContentFilter, PermissionChecker

    # Find tool
    try:
        tool = tool_registry.get_tool(tool_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    start_time = time.time()

    # Security checks
    permission_checker = PermissionChecker()
    perm_result = await permission_checker.can_use_tool(current_user, tool_name)
    if not perm_result.allowed:
        return {
            "success": False,
            "error": perm_result.reason,
            "duration_ms": int((time.time() - start_time) * 1000),
        }

    content_filter = ContentFilter()
    filter_result = await content_filter.filter_input(tool_name, tool_input)
    if filter_result.action.value == "block":
        return {
            "success": False,
            "error": f"Input blocked: {filter_result.warnings}",
            "duration_ms": int((time.time() - start_time) * 1000),
        }

    filtered_input = filter_result.modified_content or tool_input

    # Execute tool
    try:
        result = await tool.execute(**filtered_input)
        duration_ms = int((time.time() - start_time) * 1000)

        # Filter output
        output_result = await content_filter.filter_output(tool_name, result)

        return {
            "success": True,
            "result": output_result.modified_content or str(result),
            "duration_ms": duration_ms,
            "warnings": output_result.warnings,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "duration_ms": int((time.time() - start_time) * 1000),
        }
