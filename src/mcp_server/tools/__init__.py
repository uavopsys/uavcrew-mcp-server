"""MCP tools for compliance data access.

Database tools (read-only):
- list_tables: List all database tables
- describe_table: Get table columns and structure
- query_table: Query raw table data

File tools (read-only):
- list_files: List directory contents
- read_file: Read file content
- get_file_metadata: Get file info
"""

from .raw_database import list_tables, describe_table, query_table
from .list_files import list_files
from .read_file import read_file
from .file_metadata import get_file_metadata

__all__ = [
    # Database tools (raw, read-only)
    "list_tables",
    "describe_table",
    "query_table",
    # File tools (read-only)
    "list_files",
    "read_file",
    "get_file_metadata",
]
