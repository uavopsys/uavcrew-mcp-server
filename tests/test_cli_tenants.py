"""Tests for MCP Gateway tenant CLI commands.

Tests the `uavcrew tenants add/list/remove` CLI commands that manage
the tenant_id → K4 mapping in the SQLite tenant database.
"""

import os
import tempfile

import pytest
from typer.testing import CliRunner

from mcp_server.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def temp_tenant_db(monkeypatch):
    """Use a temporary SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    monkeypatch.setenv("MCP_TENANT_DB_PATH", db_path)
    # Also patch the module-level _DB_PATH
    import mcp_server.tenant_db as tdb
    monkeypatch.setattr(tdb, "_DB_PATH", db_path)
    yield db_path
    os.unlink(db_path)


class TestTenantsAdd:
    """Test `uavcrew tenants add` command."""

    def test_add_tenant(self):
        result = runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "mmx-uuid", "--token", "ak_mmx_123", "--name", "MMX Media"],
        )
        assert result.exit_code == 0
        assert "mmx-uuid" in result.output
        assert "MMX Media" in result.output

    def test_add_tenant_without_name(self):
        result = runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "sky-uuid", "--token", "ak_sky_456"],
        )
        assert result.exit_code == 0
        assert "sky-uuid" in result.output

    def test_add_existing_tenant_updates(self):
        # Add first time
        runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "mmx-uuid", "--token", "ak_old", "--name", "MMX"],
        )
        # Add again with new token
        result = runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "mmx-uuid", "--token", "ak_new", "--name", "MMX Updated"],
        )
        assert result.exit_code == 0
        assert "already exists" in result.output

        # Verify token was updated
        from mcp_server.tenant_db import get_tenant_token
        assert get_tenant_token("mmx-uuid") == "ak_new"


class TestTenantsList:
    """Test `uavcrew tenants list` command."""

    def test_list_empty(self):
        result = runner.invoke(app, ["tenants", "list"])
        assert result.exit_code == 0
        assert "No tenants" in result.output

    def test_list_with_tenants(self):
        # Add some tenants
        runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "mmx-uuid", "--token", "ak_mmx", "--name", "MMX Media"],
        )
        runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "sky-uuid", "--token", "ak_sky", "--name", "SkyShot"],
        )

        result = runner.invoke(app, ["tenants", "list"])
        assert result.exit_code == 0
        assert "mmx-uuid" in result.output
        assert "MMX Media" in result.output
        assert "sky-uuid" in result.output
        assert "SkyShot" in result.output


class TestTenantsRemove:
    """Test `uavcrew tenants remove` command."""

    def test_remove_existing(self):
        runner.invoke(
            app,
            ["tenants", "add", "--tenant-id", "mmx-uuid", "--token", "ak_mmx"],
        )

        result = runner.invoke(
            app,
            ["tenants", "remove", "--tenant-id", "mmx-uuid"],
        )
        assert result.exit_code == 0
        assert "Removed" in result.output

        # Verify it's gone
        from mcp_server.tenant_db import get_tenant_token
        assert get_tenant_token("mmx-uuid") is None

    def test_remove_nonexistent(self):
        result = runner.invoke(
            app,
            ["tenants", "remove", "--tenant-id", "doesnt-exist"],
        )
        assert result.exit_code == 0
        assert "not found" in result.output
