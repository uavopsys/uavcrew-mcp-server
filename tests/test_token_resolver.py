"""Tests for token resolver (static and dynamic modes).

Tests the TokenResolver class that replaces tenant_db.py for
resolving tenant_id → K4 (client API token).
"""

import os
import pytest
import httpx
import respx

from mcp_server.token_resolver import TokenResolver


class TestStaticMode:
    """Tests for static token resolution (single-tenant)."""

    def test_static_returns_env_var(self, monkeypatch):
        monkeypatch.setenv("CLIENT_API_TOKEN", "test-k4-token")
        resolver = TokenResolver(
            {"mode": "static", "token_env": "CLIENT_API_TOKEN"},
            "https://api.example.com",
        )
        assert resolver.mode == "static"
        assert resolver.static_token == "test-k4-token"

    @pytest.mark.anyio
    async def test_static_resolve(self, monkeypatch):
        monkeypatch.setenv("CLIENT_API_TOKEN", "test-k4-token")
        resolver = TokenResolver(
            {"mode": "static", "token_env": "CLIENT_API_TOKEN"},
            "https://api.example.com",
        )
        result = await resolver.resolve()
        assert result == "test-k4-token"

    @pytest.mark.anyio
    async def test_static_resolve_ignores_tenant_id(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "the-token")
        resolver = TokenResolver(
            {"mode": "static", "token_env": "MY_TOKEN"},
            "https://api.example.com",
        )
        result = await resolver.resolve(tenant_id="any-id", t1_jwt="any-jwt")
        assert result == "the-token"

    @pytest.mark.anyio
    async def test_static_missing_env_var(self, monkeypatch):
        monkeypatch.delenv("CLIENT_API_TOKEN", raising=False)
        resolver = TokenResolver(
            {"mode": "static", "token_env": "CLIENT_API_TOKEN"},
            "https://api.example.com",
        )
        result = await resolver.resolve()
        assert result is None

    def test_static_custom_env_var(self, monkeypatch):
        monkeypatch.setenv("CUSTOM_KEY", "custom-value")
        resolver = TokenResolver(
            {"mode": "static", "token_env": "CUSTOM_KEY"},
            "https://api.example.com",
        )
        assert resolver.static_token == "custom-value"

    def test_defaults_to_static(self, monkeypatch):
        monkeypatch.setenv("CLIENT_API_TOKEN", "default-token")
        resolver = TokenResolver({}, "https://api.example.com")
        assert resolver.mode == "static"
        assert resolver.static_token == "default-token"


class TestDynamicMode:
    """Tests for dynamic token resolution (multi-tenant)."""

    def test_dynamic_builds_resolver_url(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/internal/mcp/resolve-token"},
            "https://api.example.com/api/v1",
        )
        assert resolver.mode == "dynamic"
        assert resolver.resolver_url == "https://api.example.com/api/v1/internal/mcp/resolve-token"

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolve_success(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/internal/mcp/resolve-token"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/internal/mcp/resolve-token").mock(
            return_value=httpx.Response(
                200,
                json={"api_token": "resolved-k4-token", "organization": "Test Org"},
            )
        )

        result = await resolver.resolve(tenant_id="tenant-123", t1_jwt="valid.jwt.token")
        assert result == "resolved-k4-token"

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_sends_jwt_as_bearer(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        route = respx.post("https://api.example.com/resolve").mock(
            return_value=httpx.Response(200, json={"api_token": "k4"})
        )

        await resolver.resolve(tenant_id="t1", t1_jwt="my.jwt.here")

        assert route.called
        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer my.jwt.here"

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_sends_tenant_id_in_body(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        route = respx.post("https://api.example.com/resolve").mock(
            return_value=httpx.Response(200, json={"api_token": "k4"})
        )

        await resolver.resolve(tenant_id="org-uuid-123", t1_jwt="jwt")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["tenant_id"] == "org-uuid-123"

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolver_returns_404(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/resolve").mock(
            return_value=httpx.Response(404, json={"error": "tenant not found"})
        )

        result = await resolver.resolve(tenant_id="unknown", t1_jwt="jwt")
        assert result is None

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolver_returns_401(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/resolve").mock(
            return_value=httpx.Response(401, json={"error": "invalid token"})
        )

        result = await resolver.resolve(tenant_id="t1", t1_jwt="bad-jwt")
        assert result is None

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolver_returns_empty_token(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/resolve").mock(
            return_value=httpx.Response(200, json={"api_token": ""})
        )

        result = await resolver.resolve(tenant_id="t1", t1_jwt="jwt")
        assert result is None

    @pytest.mark.anyio
    async def test_dynamic_missing_jwt(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )
        result = await resolver.resolve(tenant_id="t1", t1_jwt=None)
        assert result is None

    @pytest.mark.anyio
    async def test_dynamic_missing_tenant_id(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )
        result = await resolver.resolve(tenant_id=None, t1_jwt="jwt")
        assert result is None

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolver_timeout(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/resolve").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await resolver.resolve(tenant_id="t1", t1_jwt="jwt")
        assert result is None

    @pytest.mark.anyio
    @respx.mock
    async def test_dynamic_resolver_connection_error(self):
        resolver = TokenResolver(
            {"mode": "dynamic", "resolver_path": "/resolve"},
            "https://api.example.com",
        )

        respx.post("https://api.example.com/resolve").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await resolver.resolve(tenant_id="t1", t1_jwt="jwt")
        assert result is None


class TestInvalidConfig:
    """Tests for invalid configuration."""

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown auth mode"):
            TokenResolver({"mode": "magic"}, "https://api.example.com")
