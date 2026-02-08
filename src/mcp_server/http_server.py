"""UAVCrew MCP Gateway.

HTTP interface for MCP tools, providing UAVCrew AI agents access to
customer data (database, files, storage) over the network.

Endpoints:
  REST (for UAVCrew client):
    GET  /health          - Health check
    GET  /mcp/tools       - List available tools
    POST /mcp/tools/call  - Call a tool

  JSON-RPC 2.0 (MCP standard):
    POST /jsonrpc         - MCP protocol endpoint (initialize, tools/list, tools/call, ping)

Tools (13):
  Database:  list_tables, describe_table, query_table
  Files:     list_files, read_file, get_file_metadata
  Storage:   storage_list, storage_get, storage_classify, storage_notes,
             storage_move, storage_quota, storage_search
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Request, Response
from pydantic import BaseModel

from . import __version__
from .tools.registry import TOOL_SCHEMAS, dispatch_tool

# MCP protocol version supported
MCP_PROTOCOL_VERSION = "2025-06-18"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    yield


# Create FastAPI app
app = FastAPI(
    title="UAVCrew MCP Gateway",
    description="MCP Gateway for UAVCrew AI agent access to customer data",
    version=__version__,
    lifespan=lifespan,
)


# =========================================================================
# Request/Response Models (REST)
# =========================================================================

class ToolCallRequest(BaseModel):
    """REST tool call request."""
    tool: str
    arguments: dict = {}


# =========================================================================
# Authentication
# =========================================================================

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


# =========================================================================
# REST Endpoints (for UAVCrew client)
# =========================================================================

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "mcp-gateway", "version": __version__}


@app.post("/mcp/tools/call")
async def call_tool_rest(
    request: ToolCallRequest,
    authorization: str | None = Header(None),
):
    """Call an MCP tool via REST."""
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    result = dispatch_tool(request.tool, request.arguments)

    # Pass through error responses from tools
    if isinstance(result, dict) and "error" in result:
        return result

    return result


@app.get("/mcp/tools")
async def list_mcp_tools(authorization: str | None = Header(None)):
    """List available MCP tools via REST."""
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return {"tools": TOOL_SCHEMAS}


# =========================================================================
# JSON-RPC 2.0 Endpoint (MCP standard protocol)
# =========================================================================

def _jsonrpc_error(id: Any, code: int, message: str) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": {"code": code, "message": message},
    }


def _jsonrpc_result(id: Any, result: Any) -> dict:
    """Build a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": result,
    }


def _handle_initialize(id: Any, params: dict) -> tuple[dict, str]:
    """Handle MCP initialize request. Returns (response, session_id)."""
    session_id = str(uuid.uuid4())

    result = {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "uavcrew-mcp-gateway",
            "version": __version__,
        },
    }

    return _jsonrpc_result(id, result), session_id


def _handle_tools_list(id: Any, params: dict) -> dict:
    """Handle MCP tools/list request."""
    tools = []
    for schema in TOOL_SCHEMAS:
        tools.append({
            "name": schema["name"],
            "description": schema["description"],
            "inputSchema": schema["inputSchema"],
        })

    return _jsonrpc_result(id, {"tools": tools})


def _handle_tools_call(id: Any, params: dict) -> dict:
    """Handle MCP tools/call request."""
    name = params.get("name")
    arguments = params.get("arguments", {})

    if not name:
        return _jsonrpc_error(id, -32602, "Missing required parameter: name")

    result = dispatch_tool(name, arguments)

    # Check for dispatch errors
    is_error = isinstance(result, dict) and (
        result.get("success") is False or "error" in result
    )

    # Wrap result in MCP content format
    return _jsonrpc_result(id, {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, indent=2, default=str),
            }
        ],
        "isError": is_error,
    })


def _handle_ping(id: Any) -> dict:
    """Handle MCP ping request."""
    return _jsonrpc_result(id, {})


@app.post("/jsonrpc")
async def jsonrpc_endpoint(
    request: Request,
    authorization: str | None = Header(None),
):
    """
    MCP JSON-RPC 2.0 endpoint.

    Supports: initialize, notifications/initialized, tools/list, tools/call, ping.
    """
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error: invalid JSON")

    # Validate JSON-RPC structure
    if not isinstance(body, dict):
        return _jsonrpc_error(None, -32600, "Invalid request: expected object")

    jsonrpc = body.get("jsonrpc")
    if jsonrpc != "2.0":
        return _jsonrpc_error(body.get("id"), -32600, "Invalid request: jsonrpc must be '2.0'")

    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id")  # None for notifications

    # Notifications (no id = no response expected)
    if method == "notifications/initialized":
        return Response(status_code=202)

    if not method:
        return _jsonrpc_error(req_id, -32600, "Invalid request: missing method")

    # Dispatch by method
    if method == "initialize":
        response, session_id = _handle_initialize(req_id, params)
        return Response(
            content=json.dumps(response),
            media_type="application/json",
            headers={"Mcp-Session-Id": session_id},
        )

    elif method == "tools/list":
        return _handle_tools_list(req_id, params)

    elif method == "tools/call":
        return _handle_tools_call(req_id, params)

    elif method == "ping":
        return _handle_ping(req_id)

    else:
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")


# =========================================================================
# Server Entry Point
# =========================================================================

def main():
    """Run the MCP Gateway."""
    import uvicorn

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8200"))

    print(f"\nStarting UAVCrew MCP Gateway on {host}:{port}")
    print(f"  REST endpoints:")
    print(f"    - Tools:    POST http://{host}:{port}/mcp/tools/call")
    print(f"    - List:     GET  http://{host}:{port}/mcp/tools")
    print(f"    - Health:   GET  http://{host}:{port}/health")
    print(f"  JSON-RPC 2.0 (MCP standard):")
    print(f"    - Endpoint: POST http://{host}:{port}/jsonrpc\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
