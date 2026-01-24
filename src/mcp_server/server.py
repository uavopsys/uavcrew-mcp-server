"""MCP Server for drone compliance data.

Provides raw database tools + file access tools.
All database operations are READ-ONLY.
"""

import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools.raw_database import list_tables, describe_table, query_table
from .tools.list_files import list_files
from .tools.read_file import read_file
from .tools.file_metadata import get_file_metadata

# Create MCP server
server = Server("compliance-mcp-server")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        # === Database Tools (Raw, Read-Only) ===
        Tool(
            name="list_tables",
            description="List all tables in the database with row counts. Call this first to discover the schema.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="describe_table",
            description="Describe a table's columns with types, primary keys, foreign keys, and sample data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Table name to describe"
                    }
                },
                "required": ["table"]
            }
        ),
        Tool(
            name="query_table",
            description="Query raw data from a table. Supports column selection, WHERE clauses, ORDER BY, and LIMIT.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Table name to query"
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Specific columns to return (default: all)"
                    },
                    "where": {
                        "type": "string",
                        "description": "Optional: WHERE clause (e.g., \"status = 'active'\")"
                    },
                    "order_by": {
                        "type": "string",
                        "description": "Optional: ORDER BY clause (e.g., \"created_at DESC\")"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum rows to return (default: 100, max: 1000)",
                        "default": 100
                    }
                },
                "required": ["table"]
            }
        ),
        # === File Access Tools ===
        Tool(
            name="list_files",
            description="List files in a directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path to list"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files",
                        "default": "*"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List recursively",
                        "default": False
                    }
                },
                "required": ["directory"]
            }
        ),
        Tool(
            name="read_file",
            description="Read file content",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read"
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding",
                        "default": "utf-8"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_file_metadata",
            description="Get file metadata (size, type, dates)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path"
                    }
                },
                "required": ["path"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool invocations."""
    try:
        # Database tools (raw, read-only)
        if name == "list_tables":
            result = list_tables()

        elif name == "describe_table":
            result = describe_table(arguments["table"])

        elif name == "query_table":
            result = query_table(
                table=arguments["table"],
                columns=arguments.get("columns"),
                where=arguments.get("where"),
                order_by=arguments.get("order_by"),
                limit=arguments.get("limit", 100),
            )

        # File access tools
        elif name == "list_files":
            result = list_files(
                arguments["directory"],
                arguments.get("pattern", "*"),
                arguments.get("recursive", False),
            )

        elif name == "read_file":
            result = read_file(
                arguments["path"],
                arguments.get("max_bytes"),
                arguments.get("encoding", "utf-8"),
            )

        elif name == "get_file_metadata":
            result = get_file_metadata(arguments["path"])

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str)
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2)
        )]


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point."""
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
