"""HTTP wrapper for MCP server.

This provides an HTTP/JSON-RPC interface to the MCP tools,
allowing the compliance service to call MCP servers over the network.
"""

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel

from .tools.flight_log import get_flight_log
from .tools.pilot import get_pilot
from .tools.aircraft import get_aircraft
from .tools.mission import get_mission
from .tools.maintenance import get_maintenance_history
from .tools.list_files import list_files
from .tools.read_file import read_file
from .tools.file_metadata import get_file_metadata
from .tools.certifications import (
    search_pilots,
    check_authorization,
    get_expiring_certifications,
    update_faa_verification,
    record_verification_audit,
    update_training_status,
    flag_certification_warning,
)
from .database import get_db, seed_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    if os.environ.get("SEED_DEMO_DATA", "true").lower() == "true":
        seed_demo_data()
    yield
    # Shutdown (nothing to do)


# Create FastAPI app
app = FastAPI(
    title="UAVCrew Compliance MCP Server",
    description="HTTP interface for MCP tools",
    version="1.0.0",
    lifespan=lifespan,
)


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    method: str
    params: dict = {}
    id: int | str | None = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    result: Any = None
    error: dict | None = None
    id: int | str | None = None


# Load API key from environment
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")


def verify_auth(authorization: str | None) -> bool:
    """Verify authorization header."""
    if not MCP_API_KEY:
        return True  # No auth if key not configured

    if not authorization:
        return False

    # Support both "Bearer <key>" and raw key
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    return token == MCP_API_KEY


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "mcp-server"}


@app.post("/mcp")
async def mcp_endpoint(
    request: JSONRPCRequest,
    authorization: str | None = Header(None),
):
    """
    MCP JSON-RPC endpoint.

    Handles tool calls in JSON-RPC 2.0 format.
    """
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # Only handle tools/call method
    if request.method != "tools/call":
        return JSONRPCResponse(
            error={"code": -32601, "message": f"Method not found: {request.method}"},
            id=request.id,
        )

    params = request.params
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if not tool_name:
        return JSONRPCResponse(
            error={"code": -32602, "message": "Missing tool name"},
            id=request.id,
        )

    # Call the appropriate tool
    db = get_db()

    try:
        if tool_name == "get_flight_log":
            result = get_flight_log(db, arguments.get("flight_id", ""))
        elif tool_name == "get_pilot":
            result = get_pilot(db, arguments.get("pilot_id", ""))
        elif tool_name == "get_aircraft":
            result = get_aircraft(db, arguments.get("aircraft_id", ""))
        elif tool_name == "get_mission":
            result = get_mission(db, arguments.get("flight_id", ""))
        elif tool_name == "get_maintenance_history":
            result = get_maintenance_history(
                db,
                arguments.get("aircraft_id", ""),
                arguments.get("limit", 10)
            )
        # File access tools (no database needed)
        elif tool_name == "list_files":
            result = list_files(
                arguments.get("directory", "."),
                arguments.get("pattern", "*"),
                arguments.get("recursive", False),
            )
        elif tool_name == "read_file":
            result = read_file(
                arguments.get("path", ""),
                arguments.get("max_bytes"),
                arguments.get("encoding", "utf-8"),
            )
        elif tool_name == "get_file_metadata":
            result = get_file_metadata(arguments.get("path", ""))
        # Certification READ tools
        elif tool_name == "search_pilots":
            result = search_pilots(
                db,
                name=arguments.get("name"),
                certificate_number=arguments.get("certificate_number"),
                certificate_type=arguments.get("certificate_type"),
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "check_authorization":
            result = check_authorization(
                db,
                arguments.get("pilot_id", ""),
                arguments.get("operation_type", "Part 107"),
                arguments.get("aircraft_id"),
            )
        elif tool_name == "get_expiring_certifications":
            result = get_expiring_certifications(
                db,
                arguments.get("days_ahead", 90),
                arguments.get("pilot_id"),
            )
        # Certification WRITE tools
        elif tool_name == "update_faa_verification":
            result = update_faa_verification(
                db,
                pilot_id=arguments.get("pilot_id", ""),
                verification_status=arguments.get("verification_status", ""),
                is_authorized=arguments.get("is_authorized", False),
                certificate_verified=arguments.get("certificate_verified", True),
                verification_source=arguments.get("verification_source", "faa_airmen_inquiry"),
                verification_details=arguments.get("verification_details"),
                verified_by=arguments.get("verified_by", "CONCORD"),
                expires_at=arguments.get("expires_at"),
            )
        elif tool_name == "record_verification_audit":
            result = record_verification_audit(
                db,
                event_type=arguments.get("event_type", ""),
                entity_type=arguments.get("entity_type", ""),
                entity_id=arguments.get("entity_id", ""),
                action=arguments.get("action", ""),
                result=arguments.get("result", ""),
                performed_by=arguments.get("performed_by", "SYSTEM"),
                details=arguments.get("details"),
                job_id=arguments.get("job_id"),
            )
        elif tool_name == "update_training_status":
            result = update_training_status(
                db,
                pilot_id=arguments.get("pilot_id", ""),
                training_type=arguments.get("training_type", ""),
                course_name=arguments.get("course_name", ""),
                completion_date=arguments.get("completion_date", ""),
                expiry_date=arguments.get("expiry_date"),
                provider=arguments.get("provider"),
                certificate_number=arguments.get("certificate_number"),
                notes=arguments.get("notes"),
                updated_by=arguments.get("updated_by", "CONCORD"),
            )
        elif tool_name == "flag_certification_warning":
            result = flag_certification_warning(
                db,
                entity_type=arguments.get("entity_type", ""),
                entity_id=arguments.get("entity_id", ""),
                warning_type=arguments.get("warning_type", ""),
                severity=arguments.get("severity", "medium"),
                title=arguments.get("title", ""),
                description=arguments.get("description", ""),
                due_date=arguments.get("due_date"),
                flagged_by=arguments.get("flagged_by", "CONCORD"),
                job_id=arguments.get("job_id"),
            )
        else:
            return JSONRPCResponse(
                error={"code": -32602, "message": f"Unknown tool: {tool_name}"},
                id=request.id,
            )

        # Format result in MCP content format
        return JSONRPCResponse(
            result={
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, default=str),
                    }
                ]
            },
            id=request.id,
        )

    except Exception as e:
        return JSONRPCResponse(
            error={"code": -32000, "message": str(e)},
            id=request.id,
        )


@app.get("/tools")
async def list_tools(authorization: str | None = Header(None)):
    """List available MCP tools."""
    if not verify_auth(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return {
        "tools": [
            {
                "name": "get_flight_log",
                "description": "Retrieve parsed flight log data for a specific flight",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "string", "description": "Unique flight identifier"}
                    },
                    "required": ["flight_id"]
                }
            },
            {
                "name": "get_pilot",
                "description": "Retrieve pilot certification and credentials",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pilot_id": {"type": "string", "description": "Pilot identifier"}
                    },
                    "required": ["pilot_id"]
                }
            },
            {
                "name": "get_aircraft",
                "description": "Retrieve aircraft registration and status",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "aircraft_id": {"type": "string", "description": "Aircraft ID"}
                    },
                    "required": ["aircraft_id"]
                }
            },
            {
                "name": "get_mission",
                "description": "Retrieve mission planning data for a flight",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "string", "description": "Flight identifier"}
                    },
                    "required": ["flight_id"]
                }
            },
            {
                "name": "get_maintenance_history",
                "description": "Retrieve maintenance records for an aircraft",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "aircraft_id": {"type": "string", "description": "Aircraft identifier"},
                        "limit": {"type": "integer", "description": "Maximum records", "default": 10}
                    },
                    "required": ["aircraft_id"]
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
            # Certification READ tools
            {
                "name": "search_pilots",
                "description": "Search pilots by name, certificate number, or type",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Partial name match"},
                        "certificate_number": {"type": "string", "description": "Certificate number"},
                        "certificate_type": {"type": "string", "description": "Part 107, Part 61, etc."},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    }
                }
            },
            {
                "name": "check_authorization",
                "description": "Check if pilot is authorized for an operation type",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pilot_id": {"type": "string", "description": "Pilot identifier"},
                        "operation_type": {"type": "string", "description": "Operation type", "default": "Part 107"},
                        "aircraft_id": {"type": "string", "description": "Optional aircraft ID"}
                    },
                    "required": ["pilot_id"]
                }
            },
            {
                "name": "get_expiring_certifications",
                "description": "Get certifications expiring within a timeframe",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "description": "Days to look ahead", "default": 90},
                        "pilot_id": {"type": "string", "description": "Optional pilot filter"}
                    }
                }
            },
            # Certification WRITE tools
            {
                "name": "update_faa_verification",
                "description": "Record FAA verification result for a pilot",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pilot_id": {"type": "string", "description": "Pilot identifier"},
                        "verification_status": {"type": "string", "description": "valid, invalid, expired, not_found"},
                        "is_authorized": {"type": "boolean", "description": "Whether pilot is authorized"},
                        "certificate_verified": {"type": "boolean", "description": "Certificate verified", "default": True},
                        "verification_source": {"type": "string", "description": "Source", "default": "faa_airmen_inquiry"},
                        "verification_details": {"type": "object", "description": "Additional details"},
                        "verified_by": {"type": "string", "description": "Agent name", "default": "CONCORD"}
                    },
                    "required": ["pilot_id", "verification_status", "is_authorized"]
                }
            },
            {
                "name": "record_verification_audit",
                "description": "Create audit trail entry for verification event",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {"type": "string", "description": "faa_check, training_update, etc."},
                        "entity_type": {"type": "string", "description": "pilot, aircraft, flight"},
                        "entity_id": {"type": "string", "description": "Entity identifier"},
                        "action": {"type": "string", "description": "Action performed"},
                        "result": {"type": "string", "description": "success, failure, warning"},
                        "performed_by": {"type": "string", "description": "Agent name"},
                        "details": {"type": "object", "description": "Additional details"},
                        "job_id": {"type": "string", "description": "Workflow job reference"}
                    },
                    "required": ["event_type", "entity_type", "entity_id", "action", "result", "performed_by"]
                }
            },
            {
                "name": "update_training_status",
                "description": "Create or update pilot training record",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pilot_id": {"type": "string", "description": "Pilot identifier"},
                        "training_type": {"type": "string", "description": "initial, recurrent, specialized"},
                        "course_name": {"type": "string", "description": "Training course name"},
                        "completion_date": {"type": "string", "description": "ISO date format"},
                        "expiry_date": {"type": "string", "description": "Optional expiry date"},
                        "provider": {"type": "string", "description": "Training provider"},
                        "certificate_number": {"type": "string", "description": "Training certificate"},
                        "notes": {"type": "string", "description": "Additional notes"},
                        "updated_by": {"type": "string", "description": "Agent name", "default": "CONCORD"}
                    },
                    "required": ["pilot_id", "training_type", "course_name", "completion_date"]
                }
            },
            {
                "name": "flag_certification_warning",
                "description": "Create certification warning/alert",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "description": "pilot or aircraft"},
                        "entity_id": {"type": "string", "description": "Entity identifier"},
                        "warning_type": {"type": "string", "description": "expiring, expired, invalid, missing_training"},
                        "severity": {"type": "string", "description": "critical, high, medium, low"},
                        "title": {"type": "string", "description": "Warning title"},
                        "description": {"type": "string", "description": "Detailed description"},
                        "due_date": {"type": "string", "description": "Optional due date (ISO format)"},
                        "flagged_by": {"type": "string", "description": "Agent name", "default": "CONCORD"},
                        "job_id": {"type": "string", "description": "Workflow job reference"}
                    },
                    "required": ["entity_type", "entity_id", "warning_type", "severity", "title", "description"]
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
    print(f"  - Endpoint: http://{host}:{port}/mcp")
    print(f"  - Health:   http://{host}:{port}/health")
    print(f"  - Tools:    http://{host}:{port}/tools\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
