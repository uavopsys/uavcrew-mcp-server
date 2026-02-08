"""
Shared tool registry for MCP Gateway.

Single source of truth for all tool schemas and dispatch.
Used by both REST and JSON-RPC endpoints.
"""

import json
import logging
from typing import Any

from .raw_database import list_tables, describe_table, query_table
from .list_files import list_files
from .read_file import read_file
from .file_metadata import get_file_metadata
from .storage import (
    storage_list,
    storage_get,
    storage_classify,
    storage_notes,
    storage_move,
    storage_quota,
    storage_search,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Tool Schemas — single source of truth for all 13 tools
# =========================================================================

TOOL_SCHEMAS = [
    # === Database Tools (Raw, Read-Only) ===
    {
        "name": "list_tables",
        "description": "List all tables in the database with row counts. Call this first to discover the schema.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "describe_table",
        "description": "Describe a table's columns with types, primary keys, foreign keys, and sample data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Table name to describe",
                },
            },
            "required": ["table"],
        },
    },
    {
        "name": "query_table",
        "description": "Query raw data from a table. Supports column selection, WHERE clauses, ORDER BY, and LIMIT.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Table name to query",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: Specific columns to return (default: all)",
                },
                "where": {
                    "type": "string",
                    "description": "Optional: WHERE clause (e.g., \"status = 'active'\")",
                },
                "order_by": {
                    "type": "string",
                    "description": "Optional: ORDER BY clause (e.g., \"created_at DESC\")",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return (default: 100, max: 1000)",
                    "default": 100,
                },
            },
            "required": ["table"],
        },
    },
    # === File Access Tools (Read-Only) ===
    {
        "name": "list_files",
        "description": "List files in a directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to list",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files",
                    "default": "*",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively",
                    "default": False,
                },
            },
            "required": ["directory"],
        },
    },
    {
        "name": "read_file",
        "description": "Read file content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum bytes to read",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_metadata",
        "description": "Get file metadata (size, type, dates).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory path",
                },
            },
            "required": ["path"],
        },
    },
    # === Storage Tools (MinIO) ===
    {
        "name": "storage_list",
        "description": "List files in organization's MinIO storage. Use prefix to filter by folder (e.g., 'flight-logs/'). Use category to filter by type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "prefix": {
                    "type": "string",
                    "description": "Path prefix filter (e.g., 'flight-logs/', 'documents/')",
                    "default": "",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category: flight_log, raw_video, processed_media, document, deliverable, asset, maintenance, certification, other",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max files to return",
                    "default": 50,
                },
            },
            "required": ["org_id"],
        },
    },
    {
        "name": "storage_get",
        "description": "Get file details including a presigned download URL. Use file_id (preferred) or object_key to identify the file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "file_id": {
                    "type": "string",
                    "description": "StorageFile UUID (preferred)",
                },
                "object_key": {
                    "type": "string",
                    "description": "Object key in bucket (alternative to file_id)",
                },
                "include_url": {
                    "type": "boolean",
                    "description": "Include presigned download URL",
                    "default": True,
                },
            },
            "required": ["org_id"],
        },
    },
    {
        "name": "storage_classify",
        "description": "Set AI classification metadata on a file. Use this after analyzing file content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "file_id": {
                    "type": "string",
                    "description": "StorageFile UUID",
                },
                "ai_category": {
                    "type": "string",
                    "description": "AI-detected category",
                },
                "ai_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "AI-detected tags/keywords",
                },
                "ai_summary": {
                    "type": "string",
                    "description": "AI-generated summary of file content",
                },
            },
            "required": ["org_id", "file_id"],
        },
    },
    {
        "name": "storage_notes",
        "description": "Add or update notes and tags on a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "file_id": {
                    "type": "string",
                    "description": "StorageFile UUID",
                },
                "description": {
                    "type": "string",
                    "description": "Description/notes text",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add (merged with existing)",
                },
                "append_description": {
                    "type": "boolean",
                    "description": "If true, append to existing description",
                    "default": False,
                },
            },
            "required": ["org_id", "file_id"],
        },
    },
    {
        "name": "storage_move",
        "description": "Move a file to a different category/folder. Valid categories: flight_log, raw_video, processed_media, document, deliverable, asset, maintenance, certification, other.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "file_id": {
                    "type": "string",
                    "description": "StorageFile UUID",
                },
                "new_category": {
                    "type": "string",
                    "description": "Target category",
                },
            },
            "required": ["org_id", "file_id", "new_category"],
        },
    },
    {
        "name": "storage_quota",
        "description": "Get storage quota and usage statistics for an organization.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
            },
            "required": ["org_id"],
        },
    },
    {
        "name": "storage_search",
        "description": "Search files by filename, description, or AI summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {
                    "type": "string",
                    "description": "Organization UUID",
                },
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["org_id", "query"],
        },
    },
]


# =========================================================================
# Tool Dispatch — single router for all tool calls
# =========================================================================

# Map tool names to their handler functions
_TOOL_HANDLERS = {
    # Database tools
    "list_tables": lambda args: list_tables(),
    "describe_table": lambda args: describe_table(args["table"]),
    "query_table": lambda args: query_table(
        table=args["table"],
        columns=args.get("columns"),
        where=args.get("where"),
        order_by=args.get("order_by"),
        limit=args.get("limit", 100),
    ),
    # File tools
    "list_files": lambda args: list_files(
        args["directory"],
        args.get("pattern", "*"),
        args.get("recursive", False),
    ),
    "read_file": lambda args: read_file(
        args["path"],
        args.get("max_bytes"),
        args.get("encoding", "utf-8"),
    ),
    "get_file_metadata": lambda args: get_file_metadata(args["path"]),
    # Storage tools
    "storage_list": lambda args: storage_list(
        org_id=args["org_id"],
        prefix=args.get("prefix", ""),
        category=args.get("category"),
        limit=args.get("limit", 50),
    ),
    "storage_get": lambda args: storage_get(
        org_id=args["org_id"],
        file_id=args.get("file_id"),
        object_key=args.get("object_key"),
        include_url=args.get("include_url", True),
    ),
    "storage_classify": lambda args: storage_classify(
        org_id=args["org_id"],
        file_id=args["file_id"],
        ai_category=args.get("ai_category"),
        ai_tags=args.get("ai_tags"),
        ai_summary=args.get("ai_summary"),
    ),
    "storage_notes": lambda args: storage_notes(
        org_id=args["org_id"],
        file_id=args["file_id"],
        description=args.get("description"),
        tags=args.get("tags"),
        append_description=args.get("append_description", False),
    ),
    "storage_move": lambda args: storage_move(
        org_id=args["org_id"],
        file_id=args["file_id"],
        new_category=args["new_category"],
    ),
    "storage_quota": lambda args: storage_quota(org_id=args["org_id"]),
    "storage_search": lambda args: storage_search(
        org_id=args["org_id"],
        query=args["query"],
        category=args.get("category"),
        limit=args.get("limit", 20),
    ),
}


def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a tool call to the correct handler.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        Tool result dict

    Raises:
        ValueError: If tool name is unknown
    """
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        return {"success": False, "error": f"Unknown tool: {name}"}

    try:
        result = handler(arguments)

        # Validate required arguments by checking for KeyError
        # (handlers raise KeyError for missing required args)
        return result

    except KeyError as e:
        return {"success": False, "error": f"Missing required argument: {e}"}
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return {"success": False, "error": str(e)}


def get_tool_names() -> list[str]:
    """Get list of all registered tool names."""
    return list(_TOOL_HANDLERS.keys())
