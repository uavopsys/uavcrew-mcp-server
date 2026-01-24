"""HTTP wrapper for MCP server.

This provides an HTTP/JSON interface to the MCP tools,
allowing UAVCrew to call MCP servers over the network.

Tools available:
- Database: list_tables, describe_table, query_table
- File access: list_files, read_file, get_file_metadata
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from . import __version__
from .tools.raw_database import list_tables, describe_table, query_table
from .tools.list_files import list_files
from .tools.read_file import read_file
from .tools.file_metadata import get_file_metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    yield


# Create FastAPI app
app = FastAPI(
    title="UAVCrew MCP Server",
    description="HTTP interface for MCP compliance data tools",
    version=__version__,
    lifespan=lifespan,
)


class ToolCallRequest(BaseModel):
    """Simple tool call request."""
    tool: str
    arguments: dict = {}


class ToolCallResponse(BaseModel):
    """Tool call response."""
    success: bool = True
    data: Any = None
    error: str | None = None


# Load API keys from environment
# Supports both single key (MCP_API_KEY) and multiple (MCP_API_KEYS, comma-separated)
def _load_api_keys() -> set[str]:
    """Load all configured API keys."""
    keys = set()

    # Single key (backwards compatible)
    single_key = os.environ.get("MCP_API_KEY", "").strip()
    if single_key:
        keys.add(single_key)

    # Multiple keys (comma-separated)
    multi_keys = os.environ.get("MCP_API_KEYS", "").strip()
    if multi_keys:
        for key in multi_keys.split(","):
            key = key.strip()
            if key:
                keys.add(key)

    return keys


MCP_API_KEYS = _load_api_keys()


def verify_auth(authorization: str | None) -> bool:
    """Verify authorization header against configured API keys."""
    if not MCP_API_KEYS:
        return True  # No auth if no keys configured

    if not authorization:
        return False

    # Support both "Bearer <key>" and raw key
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    return token in MCP_API_KEYS


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "mcp-server", "version": __version__}


@app.post("/mcp/tools/call")
async def call_tool(
    request: ToolCallRequest,
    authorization: str | None = Header(None),
):
    """
    Call an MCP tool.

    Simple JSON interface for tool calls.
    """
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    tool_name = request.tool
    arguments = request.arguments

    try:
        # Database tools (raw, read-only)
        if tool_name == "list_tables":
            result = list_tables()

        elif tool_name == "describe_table":
            table = arguments.get("table")
            if not table:
                return {"success": False, "error": "Missing required argument: table"}
            result = describe_table(table)

        elif tool_name == "query_table":
            table = arguments.get("table")
            if not table:
                return {"success": False, "error": "Missing required argument: table"}
            result = query_table(
                table=table,
                columns=arguments.get("columns"),
                where=arguments.get("where"),
                order_by=arguments.get("order_by"),
                limit=arguments.get("limit", 100),
            )

        # File access tools
        elif tool_name == "list_files":
            directory = arguments.get("directory")
            if not directory:
                return {"success": False, "error": "Missing required argument: directory"}
            result = list_files(
                directory,
                arguments.get("pattern", "*"),
                arguments.get("recursive", False),
            )

        elif tool_name == "read_file":
            path = arguments.get("path")
            if not path:
                return {"success": False, "error": "Missing required argument: path"}
            result = read_file(
                path,
                arguments.get("max_bytes"),
                arguments.get("encoding", "utf-8"),
            )

        elif tool_name == "get_file_metadata":
            path = arguments.get("path")
            if not path:
                return {"success": False, "error": "Missing required argument: path"}
            result = get_file_metadata(path)

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        # Check if result contains an error
        if isinstance(result, dict) and "error" in result:
            return result  # Pass through error response

        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/mcp/tools")
async def list_mcp_tools(authorization: str | None = Header(None)):
    """List available MCP tools."""
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return {
        "tools": [
            # Database tools (raw, read-only)
            {
                "name": "list_tables",
                "description": "List all tables in the database with row counts. Call this first to discover the schema.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "describe_table",
                "description": "Describe a table's columns with types, primary keys, foreign keys, and sample data.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "description": "Table name to describe"}
                    },
                    "required": ["table"]
                }
            },
            {
                "name": "query_table",
                "description": "Query raw data from a table. Supports column selection, WHERE clauses, ORDER BY, and LIMIT.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "description": "Table name"},
                        "columns": {"type": "array", "items": {"type": "string"}, "description": "Optional: Specific columns to return"},
                        "where": {"type": "string", "description": "Optional: WHERE clause (e.g., \"status = 'active'\")"},
                        "order_by": {"type": "string", "description": "Optional: ORDER BY clause (e.g., \"created_at DESC\")"},
                        "limit": {"type": "integer", "description": "Maximum rows (default: 100, max: 1000)", "default": 100}
                    },
                    "required": ["table"]
                }
            },
            # File access tools
            {
                "name": "list_files",
                "description": "List files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Directory path to list"},
                        "pattern": {"type": "string", "description": "Glob pattern to filter files", "default": "*"},
                        "recursive": {"type": "boolean", "description": "List recursively", "default": False}
                    },
                    "required": ["directory"]
                }
            },
            {
                "name": "read_file",
                "description": "Read file content",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                        "max_bytes": {"type": "integer", "description": "Maximum bytes to read"},
                        "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "get_file_metadata",
                "description": "Get file metadata (size, type, dates)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File or directory path"}
                    },
                    "required": ["path"]
                }
            },
        ]
    }


def main():
    """Run the HTTP server."""
    import uvicorn

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8200"))

    print(f"\nStarting MCP HTTP Server on {host}:{port}")
    print(f"  - Tools:    POST http://{host}:{port}/mcp/tools/call")
    print(f"  - List:     GET  http://{host}:{port}/mcp/tools")
    print(f"  - Health:   GET  http://{host}:{port}/health\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
