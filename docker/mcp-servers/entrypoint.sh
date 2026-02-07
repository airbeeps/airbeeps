#!/bin/bash
set -e

# MCP Server Entrypoint Script
# Usage: entrypoint.sh <server-name> [args...]
#
# Available servers:
#   brave-search   - Web search using Brave API
#   filesystem     - File operations (scoped to /data)
#   sqlite         - SQLite database queries
#   memory         - In-memory storage
#   fetch          - HTTP fetch operations
#   custom         - Run custom Python MCP server

SERVER_NAME="${1:-help}"
shift || true

case "$SERVER_NAME" in
    brave-search)
        # Requires BRAVE_API_KEY environment variable
        if [ -z "$BRAVE_API_KEY" ]; then
            echo "Error: BRAVE_API_KEY environment variable is required"
            exit 1
        fi
        exec npx -y @modelcontextprotocol/server-brave-search
        ;;

    filesystem)
        # Default to /data/uploads for safety
        ALLOWED_DIR="${ALLOWED_DIR:-/data/uploads}"
        echo "Starting filesystem server with allowed directory: $ALLOWED_DIR"
        exec npx -y @modelcontextprotocol/server-filesystem "$ALLOWED_DIR" "$@"
        ;;

    sqlite)
        # Database path as argument or environment variable
        DB_PATH="${1:-${SQLITE_DB_PATH:-/data/database.db}}"
        echo "Starting SQLite server with database: $DB_PATH"
        exec npx -y @modelcontextprotocol/server-sqlite "$DB_PATH"
        ;;

    memory)
        echo "Starting memory server"
        exec npx -y @modelcontextprotocol/server-memory "$@"
        ;;

    fetch)
        echo "Starting fetch server"
        exec python -m mcp_server_fetch "$@"
        ;;

    custom)
        # Run custom Python MCP server
        # Usage: custom /path/to/server.py
        SCRIPT_PATH="${1}"
        if [ -z "$SCRIPT_PATH" ]; then
            echo "Error: Script path required for custom server"
            exit 1
        fi
        shift
        exec python "$SCRIPT_PATH" "$@"
        ;;

    help|--help|-h)
        echo "Airbeeps MCP Server Container"
        echo ""
        echo "Usage: docker run airbeeps/mcp-servers <server-name> [args...]"
        echo ""
        echo "Available servers:"
        echo "  brave-search   - Web search (requires BRAVE_API_KEY)"
        echo "  filesystem     - File operations (scoped to ALLOWED_DIR)"
        echo "  sqlite         - SQLite database (DB path as arg)"
        echo "  memory         - In-memory storage"
        echo "  fetch          - HTTP fetch operations"
        echo "  custom         - Run custom Python script"
        echo ""
        echo "Environment variables:"
        echo "  BRAVE_API_KEY  - API key for Brave Search"
        echo "  ALLOWED_DIR    - Directory for filesystem server (default: /data/uploads)"
        echo "  SQLITE_DB_PATH - Path to SQLite database"
        echo ""
        echo "Examples:"
        echo "  docker run -e BRAVE_API_KEY=xxx airbeeps/mcp-servers brave-search"
        echo "  docker run -v ./data:/data airbeeps/mcp-servers filesystem /data/uploads"
        echo "  docker run -v ./db.sqlite:/data/db.sqlite airbeeps/mcp-servers sqlite /data/db.sqlite"
        ;;

    *)
        echo "Unknown server: $SERVER_NAME"
        echo "Run with --help for available servers"
        exit 1
        ;;
esac
