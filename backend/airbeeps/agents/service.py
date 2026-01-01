"""
Agent Service - Business logic for MCP Server operations
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .mcp.registry import mcp_registry
from .models import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPServerService:
    """MCP server configuration service"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_mcp_server(self, server_data: dict[str, Any]) -> MCPServerConfig:
        """Create MCP server configuration"""
        logger.info(f"Creating MCP server: {server_data.get('name')}")
        logger.debug(f"Server config: {server_data}")

        server = MCPServerConfig(**server_data)

        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        logger.debug(f"Created MCP server with ID: {server.id}")

        # Try to register with MCP registry
        if server.is_active:
            try:
                logger.debug(f"Registering MCP server {server.name} with registry")
                await mcp_registry.register_server(server)
                logger.info(f"Successfully registered MCP server: {server.name}")
            except Exception as e:
                logger.error(
                    f"Failed to register MCP server {server.name}: {e}", exc_info=True
                )

        return server

    async def get_mcp_server(self, server_id: uuid.UUID) -> MCPServerConfig | None:
        """Get MCP server by ID"""
        logger.debug(f"Retrieving MCP server {server_id}")
        stmt = select(MCPServerConfig).where(MCPServerConfig.id == server_id)
        result = await self.session.execute(stmt)
        server = result.scalar_one_or_none()
        if server:
            logger.debug(f"Found MCP server: {server.name}")
        else:
            logger.debug(f"MCP server {server_id} not found")
        return server

    async def list_mcp_servers(self) -> list[MCPServerConfig]:
        """List all MCP servers"""
        logger.debug("Listing all MCP servers")
        stmt = select(MCPServerConfig)
        result = await self.session.execute(stmt)
        servers = list(result.scalars().all())
        logger.debug(f"Retrieved {len(servers)} MCP servers")
        return servers

    async def delete_mcp_server(self, server_id: uuid.UUID) -> bool:
        """Delete MCP server"""
        logger.info(f"Deleting MCP server {server_id}")
        server = await self.get_mcp_server(server_id)
        if not server:
            logger.warning(f"MCP server {server_id} not found for deletion")
            return False

        # Unregister from MCP registry
        if mcp_registry.is_registered(server.name):
            logger.debug(f"Unregistering MCP server {server.name} from registry")
            await mcp_registry.unregister_server(server.name)

        await self.session.delete(server)
        await self.session.commit()
        logger.info(f"Successfully deleted MCP server: {server.name} ({server_id})")

        return True
