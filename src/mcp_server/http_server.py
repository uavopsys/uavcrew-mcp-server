"""HTTP wrapper for MCP server.

This provides an HTTP/JSON interface to the MCP tools,
allowing UAVCrew to call MCP servers over the network.

Tools available:
- list_entities: Discover available data
- describe_entity: See fields for an entity
- query_entity: Query data with filters
- list_files, read_file, get_file_metadata: File access
"""

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from .tools.database import list_entities, describe_entity, query_entity
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
    version="2.0.0",
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
    return {"status": "healthy", "service": "mcp-server", "version": "2.0.0"}


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
        # Database tools (read-only)
        if tool_name == "list_entities":
            result = list_entities()

        elif tool_name == "describe_entity":
            entity = arguments.get("entity")
            if not entity:
                return {"success": False, "error": "Missing required argument: entity"}
            result = describe_entity(entity)

        elif tool_name == "query_entity":
            entity = arguments.get("entity")
            if not entity:
                return {"success": False, "error": "Missing required argument: entity"}
            result = query_entity(
                entity=entity,
                id=arguments.get("id"),
                filters=arguments.get("filters"),
                fields=arguments.get("fields"),
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
async def list_tools(authorization: str | None = Header(None)):
    """List available MCP tools."""
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return {
        "tools": [
            # Database tools (generic, read-only)
            {
                "name": "list_entities",
                "description": "List all available data entities. Call this first to see what data is available.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "describe_entity",
                "description": "Describe the fields available for a specific entity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity": {"type": "string", "description": "Entity name (e.g., pilots, aircraft, flights)"}
                    },
                    "required": ["entity"]
                }
            },
            {
                "name": "query_entity",
                "description": "Query data from an entity. Get single record by ID, or multiple records with filters.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity": {"type": "string", "description": "Entity name"},
                        "id": {"type": "string", "description": "Optional: Get single record by ID"},
                        "filters": {"type": "object", "description": "Optional: Filter conditions as {field: value}"},
                        "fields": {"type": "array", "items": {"type": "string"}, "description": "Optional: Specific fields to return"},
                        "limit": {"type": "integer", "description": "Maximum records (default: 100)", "default": 100}
                    },
                    "required": ["entity"]
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
