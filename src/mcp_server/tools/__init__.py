"""MCP tools for compliance data access.

Database tools (read-only):
- list_tables: List all database tables
- describe_table: Get table columns and structure
- query_table: Query raw table data

File tools (read-only):
- list_files: List directory contents
- read_file: Read file content
- get_file_metadata: Get file info

Storage tools (MinIO):
- storage_list: List files in org storage
- storage_get: Get file with download URL
- storage_classify: Set AI classification
- storage_notes: Add notes to files
- storage_move: Move files between categories
- storage_quota: Get storage quota/usage
- storage_search: Search files
"""

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

__all__ = [
    # Database tools (raw, read-only)
    "list_tables",
    "describe_table",
    "query_table",
    # File tools (read-only)
    "list_files",
    "read_file",
    "get_file_metadata",
    # Storage tools (MinIO)
    "storage_list",
    "storage_get",
    "storage_classify",
    "storage_notes",
    "storage_move",
    "storage_quota",
    "storage_search",
]
