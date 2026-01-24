"""
Raw database introspection tools for MCP server.

These tools expose the actual database schema without pre-mapping,
allowing UAVCrew to discover and map the schema on its side.

Tools:
- list_tables() - Get all table names
- describe_table(table) - Get columns with types
- query_table(table, ...) - Query raw data
"""

import os
from typing import Optional

from sqlalchemy import create_engine, inspect, text


def _get_engine():
    """Get database engine from environment."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None
    return create_engine(db_url)


def list_tables() -> dict:
    """
    List all tables in the database.

    Returns:
        Dictionary with table names and row counts
    """
    engine = _get_engine()
    if not engine:
        return {
            "error": "DATABASE_URL not configured",
            "tables": [],
        }

    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # Get row counts for each table
        tables = []
        with engine.connect() as conn:
            for name in table_names:
                try:
                    result = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"'))
                    count = result.scalar()
                except Exception:
                    count = None
                tables.append({
                    "name": name,
                    "row_count": count,
                })

        return {
            "tables": tables,
            "count": len(tables),
        }
    except Exception as e:
        return {
            "error": str(e),
            "tables": [],
        }


def describe_table(table: str) -> dict:
    """
    Describe a table's columns with types.

    Args:
        table: Table name

    Returns:
        Dictionary with column details
    """
    engine = _get_engine()
    if not engine:
        return {"error": "DATABASE_URL not configured"}

    try:
        inspector = inspect(engine)

        # Check table exists
        if table not in inspector.get_table_names():
            return {
                "error": f"Table '{table}' not found",
                "available_tables": inspector.get_table_names(),
            }

        # Get columns
        columns = []
        for col in inspector.get_columns(table):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": str(col.get("default")) if col.get("default") else None,
                "primary_key": col.get("primary_key", False),
            })

        # Get primary key
        pk = inspector.get_pk_constraint(table)
        pk_columns = pk.get("constrained_columns", []) if pk else []

        # Get foreign keys
        fks = []
        for fk in inspector.get_foreign_keys(table):
            fks.append({
                "columns": fk.get("constrained_columns", []),
                "references_table": fk.get("referred_table"),
                "references_columns": fk.get("referred_columns", []),
            })

        # Get sample data (first 3 rows)
        sample = []
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f'SELECT * FROM "{table}" LIMIT 3'))
                for row in result:
                    sample.append(dict(row._mapping))
        except Exception:
            pass

        return {
            "table": table,
            "columns": columns,
            "primary_key": pk_columns,
            "foreign_keys": fks,
            "sample_data": sample,
        }
    except Exception as e:
        return {"error": str(e)}


def query_table(
    table: str,
    columns: Optional[list[str]] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """
    Query raw data from a table.

    Args:
        table: Table name
        columns: Optional list of columns (default: all)
        where: Optional WHERE clause (e.g., "status = 'active'")
        order_by: Optional ORDER BY clause (e.g., "created_at DESC")
        limit: Maximum rows (default: 100, max: 1000)

    Returns:
        Dictionary with query results
    """
    engine = _get_engine()
    if not engine:
        return {"error": "DATABASE_URL not configured"}

    # Safety limits
    limit = min(limit, 1000)

    try:
        inspector = inspect(engine)

        # Check table exists
        if table not in inspector.get_table_names():
            return {
                "error": f"Table '{table}' not found",
                "available_tables": inspector.get_table_names(),
            }

        # Build query
        if columns:
            # Validate columns exist
            valid_columns = [c["name"] for c in inspector.get_columns(table)]
            invalid = [c for c in columns if c not in valid_columns]
            if invalid:
                return {
                    "error": f"Invalid columns: {invalid}",
                    "valid_columns": valid_columns,
                }
            select_clause = ", ".join(f'"{c}"' for c in columns)
        else:
            select_clause = "*"

        query = f'SELECT {select_clause} FROM "{table}"'

        if where:
            # Basic SQL injection prevention - only allow simple conditions
            # In production, use parameterized queries
            if any(kw in where.upper() for kw in ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "--", ";"]):
                return {"error": "Invalid WHERE clause"}
            query += f" WHERE {where}"

        if order_by:
            query += f" ORDER BY {order_by}"

        query += f" LIMIT {limit}"

        # Execute
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = [dict(row._mapping) for row in result]

        return {
            "table": table,
            "data": rows,
            "count": len(rows),
            "limit": limit,
        }
    except Exception as e:
        return {"error": str(e)}
