"""Tests for MCP Gateway tenant HTTP API.

Tests the GET/POST/DELETE /tenants endpoints for programmatic
tenant management (used by Phase 7 onboarding and manual testing).
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import mcp_server.tenant_db as tdb
from mcp_server.server import app


@pytest.fixture(autouse=True)
def temp_tenant_db(monkeypatch):
    """Use a temporary SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    monkeypatch.setenv("MCP_TENANT_DB_PATH", db_path)
    monkeypatch.setattr(tdb, "_DB_PATH", db_path)
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def client():
    """FastAPI test client (no auth — dev mode with no keys configured)."""
    return TestClient(app)


class TestListTenants:
    def test_list_empty(self, client):
        response = client.get("/tenants")
        assert response.status_code == 200
        data = response.json()
        assert data["tenants"] == []
        assert data["total"] == 0

    def test_list_after_add(self, client):
        tdb.add_tenant("mmx-uuid", "ak_mmx_123", "MMX Media")
        tdb.add_tenant("sky-uuid", "ak_sky_456", "SkyShot")

        response = client.get("/tenants")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        ids = {t["tenant_id"] for t in data["tenants"]}
        assert ids == {"mmx-uuid", "sky-uuid"}

    def test_list_does_not_expose_tokens(self, client):
        tdb.add_tenant("mmx-uuid", "secret_token_123", "MMX")

        response = client.get("/tenants")
        body = response.text
        assert "secret_token_123" not in body


class TestAddTenant:
    def test_add_tenant(self, client):
        response = client.post("/tenants", json={
            "tenant_id": "mmx-uuid",
            "api_token": "ak_mmx_123",
            "name": "MMX Media",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == "mmx-uuid"
        assert data["action"] == "registered"

        # Verify stored
        assert tdb.get_tenant_token("mmx-uuid") == "ak_mmx_123"

    def test_add_without_name(self, client):
        response = client.post("/tenants", json={
            "tenant_id": "sky-uuid",
            "api_token": "ak_sky_456",
        })
        assert response.status_code == 201
        assert response.json()["name"] == ""

    def test_add_existing_updates(self, client):
        client.post("/tenants", json={
            "tenant_id": "mmx-uuid",
            "api_token": "old_token",
        })
        response = client.post("/tenants", json={
            "tenant_id": "mmx-uuid",
            "api_token": "new_token",
            "name": "Updated",
        })
        assert response.status_code == 201
        assert response.json()["action"] == "updated"
        assert tdb.get_tenant_token("mmx-uuid") == "new_token"

    def test_add_missing_tenant_id(self, client):
        response = client.post("/tenants", json={
            "api_token": "ak_123",
        })
        assert response.status_code == 400
        assert "tenant_id" in response.json()["error"]

    def test_add_missing_api_token(self, client):
        response = client.post("/tenants", json={
            "tenant_id": "mmx-uuid",
        })
        assert response.status_code == 400
        assert "api_token" in response.json()["error"]


class TestRemoveTenant:
    def test_remove_existing(self, client):
        tdb.add_tenant("mmx-uuid", "ak_mmx", "MMX")

        response = client.delete("/tenants/mmx-uuid")
        assert response.status_code == 200
        assert response.json()["action"] == "removed"

        # Verify gone
        assert tdb.get_tenant_token("mmx-uuid") is None

    def test_remove_nonexistent(self, client):
        response = client.delete("/tenants/doesnt-exist")
        assert response.status_code == 404
        assert "not found" in response.json()["error"]


class TestHealthIncludesTenants:
    def test_health_shows_tenant_count(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["tenants"] == 0

        tdb.add_tenant("mmx-uuid", "ak_mmx", "MMX")
        response = client.get("/health")
        assert response.json()["tenants"] == 1
