# MCP Servers Docker Image
# Bundles common MCP servers for easy deployment

FROM node:20-slim AS node-base

# Install Node.js MCP servers globally
RUN npm install -g \
    @modelcontextprotocol/server-brave-search@latest \
    @modelcontextprotocol/server-filesystem@latest \
    @modelcontextprotocol/server-sqlite@latest \
    @modelcontextprotocol/server-memory@latest \
    @modelcontextprotocol/server-fetch@latest \
    && npm cache clean --force

# Python stage
FROM python:3.12-slim AS python-base

# Install Python MCP servers
RUN pip install --no-cache-dir \
    mcp-server-fetch \
    mcp-server-time \
    fastmcp

# Final image
FROM python:3.12-slim

# Copy Node.js from node stage
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-base /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node-base /usr/local/bin/npm /usr/local/bin/npm

# Copy Python packages
COPY --from=python-base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-base /usr/local/bin /usr/local/bin

# Set up non-root user for security
RUN useradd -m -u 1000 mcp && \
    mkdir -p /app /data && \
    chown -R mcp:mcp /app /data

USER mcp
WORKDIR /app

# Create directories for file operations (scoped)
RUN mkdir -p /data/uploads /data/temp

# Copy entrypoint script
COPY --chown=mcp:mcp entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Environment variables
ENV NODE_PATH=/usr/local/lib/node_modules
ENV PATH="/usr/local/bin:${PATH}"

# Default command
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--help"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "console.log('healthy')" || exit 1

# Labels
LABEL maintainer="Airbeeps Team"
LABEL description="MCP Servers for Airbeeps Agent System"
LABEL version="1.0.0"
