"""MCP tools for compliance data access.

Schema discovery tools (read-only):
- list_tables: List all database tables
- describe_table: Get table columns and structure
- query_table: Query raw table data

Mapped entity tools (read-only):
- list_entities: Discover available mapped entities
- describe_entity: See fields for an entity
- query_entity: Query data with filters

File tools (read-only):
- list_files: List directory contents
- read_file: Read file content
- get_file_metadata: Get file info
"""

from .raw_database import list_tables, describe_table, query_table
from .database import list_entities, describe_entity, query_entity
from .list_files import list_files
from .read_file import read_file
from .file_metadata import get_file_metadata

__all__ = [
    # Schema discovery tools (raw database)
    "list_tables",
    "describe_table",
    "query_table",
    # Mapped entity tools
    "list_entities",
    "describe_entity",
    "query_entity",
    # File tools (read-only)
    "list_files",
    "read_file",
    "get_file_metadata",
]
