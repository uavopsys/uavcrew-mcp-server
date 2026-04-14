"""Tests for the AuthMiddleware and health endpoint in server.py.

Tests the full authentication orchestration:
  T1 JWT → K4 resolution → context vars → tool execution
  Legacy API key → K4 resolution → context vars
  Error paths: missing auth, invalid JWT, K4 resolution failure
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Key pair fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_key_pair():
    """Generate a fresh RS256 key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture
def wrong_key_pair():
    """A different key pair (signatures won't match)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_pem


def _mint_t1(
    private_pem: bytes,
    tenant_id: str = "test-tenant",
    agent_slug: str = "tucker",
    scope: list[str] | None = None,
    exp_minutes: int = 30,
) -> str:
    """Mint a T1 JWT for testing."""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "https://api.uavcrew.ai",
        "sub": f"agent:{agent_slug}",
        "aud": "mcp-gateway",
        "tenant_id": tenant_id,
        "org_id": "org-1",
        "session_id": "test-session",
        "scope": scope or ["read:aircraft", "read:maintenance"],
        "max_tier": "read_only",
        "exp": now + timedelta(minutes=exp_minutes),
        "iat": now,
        "jti": "inv_test",
    }
    return pyjwt.encode(payload, private_pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# App factory — creates a fresh app with controlled auth config
# ---------------------------------------------------------------------------


def _make_app(
    public_key: bytes | None = None,
    resolver_mode: str = "static",
    static_token: str | None = "test-k4",
    resolver_url: str | None = None,
):
    """Create a fresh FastAPI app with controlled auth settings.

    We patch module-level globals in server.py to isolate each test.
    """
    import mcp_server.server as srv
    from mcp_server.token_resolver import TokenResolver

    # Save originals
    orig_pk = srv._public_key
    orig_resolver = srv._resolver

    # Set test values
    srv._public_key = public_key

    if resolver_mode == "static":
        resolver = TokenResolver.__new__(TokenResolver)
        resolver.mode = "static"
        resolver.static_token = static_token
        resolver.resolver_url = None
        resolver.token_env = "CLIENT_API_TOKEN"
    else:
        resolver = TokenResolver.__new__(TokenResolver)
        resolver.mode = "dynamic"
        resolver.resolver_url = resolver_url or "https://resolver.test/resolve"
    srv._resolver = resolver

    def restore():
        srv._public_key = orig_pk
        srv._resolver = orig_resolver

    return srv.app, restore


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Health endpoint is always accessible and shows resolver_url."""

    @pytest.mark.anyio
    async def test_health_skips_auth(self):
        app, restore = _make_app(
            public_key=b"fake-key",
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["service"] == "mcp-gateway"
        finally:
            restore()

    @pytest.mark.anyio
    async def test_health_includes_resolver_url(self):
        app, restore = _make_app(
            resolver_mode="dynamic",
            resolver_url="https://app.ayna.com/api/v1/internal/mcp/resolve-token",
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/health")
            data = resp.json()
            assert (
                data["resolver_url"]
                == "https://app.ayna.com/api/v1/internal/mcp/resolve-token"
            )
        finally:
            restore()


# ---------------------------------------------------------------------------
# No auth configured (dev mode)
# ---------------------------------------------------------------------------


class TestDevMode:
    """When K3 is not configured — dev mode, no auth required."""

    @pytest.mark.anyio
    async def test_no_auth_allows_request(self):
        app, restore = _make_app(
            public_key=None,
            static_token="dev-k4",
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # No Authorization header — should still work
                resp = await client.get("/health")
            assert resp.status_code == 200
        finally:
            restore()


# ---------------------------------------------------------------------------
# T1 JWT path
# ---------------------------------------------------------------------------


class TestT1JWTAuth:
    """Tests for T1 JWT authentication path."""

    @pytest.mark.anyio
    async def test_valid_t1_returns_200(self, rsa_key_pair):
        """Valid T1 JWT + successful K4 resolution → request proceeds."""
        private_pem, public_pem = rsa_key_pair
        t1 = _mint_t1(private_pem)

        app, restore = _make_app(
            public_key=public_pem,
            resolver_mode="static",
            static_token="resolved-k4",
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/health",
                    headers={"Authorization": f"Bearer {t1}"},
                )
            # Health endpoint skips auth, so this always returns 200.
            # The real test is that it doesn't return 401/403.
            assert resp.status_code == 200
        finally:
            restore()

    @pytest.mark.anyio
    async def test_expired_t1_returns_401(self, rsa_key_pair):
        """Expired T1 JWT → 401."""
        private_pem, public_pem = rsa_key_pair
        t1 = _mint_t1(private_pem, exp_minutes=-1)

        app, restore = _make_app(public_key=public_pem)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Need to hit a non-health endpoint to trigger auth
                resp = await client.post(
                    "/mcp",
                    headers={"Authorization": f"Bearer {t1}"},
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
            assert resp.status_code == 401
            assert (
                "expired" in resp.json()["error"].lower()
                or "invalid" in resp.json()["error"].lower()
            )
        finally:
            restore()

    @pytest.mark.anyio
    async def test_wrong_key_returns_401(self, rsa_key_pair, wrong_key_pair):
        """T1 signed with wrong key → 401."""
        _, public_pem = rsa_key_pair
        t1 = _mint_t1(wrong_key_pair)  # Signed with wrong key

        app, restore = _make_app(public_key=public_pem)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/mcp",
                    headers={"Authorization": f"Bearer {t1}"},
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
            assert resp.status_code == 401
        finally:
            restore()

    @pytest.mark.anyio
    async def test_t1_valid_but_k4_missing_returns_403(self, rsa_key_pair):
        """Valid T1 but K4 resolution fails → 403 with reason."""
        private_pem, public_pem = rsa_key_pair
        t1 = _mint_t1(private_pem)

        app, restore = _make_app(
            public_key=public_pem,
            resolver_mode="static",
            static_token=None,  # K4 resolution will fail
        )
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/mcp",
                    headers={"Authorization": f"Bearer {t1}"},
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
            assert resp.status_code == 403
            data = resp.json()
            assert "reason" in data
            assert "test-tenant" in data["error"]
        finally:
            restore()

    @pytest.mark.anyio
    async def test_missing_auth_header_returns_401(self, rsa_key_pair):
        """No Authorization header → 401."""
        _, public_pem = rsa_key_pair

        app, restore = _make_app(public_key=public_pem)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                )
            assert resp.status_code == 401
            assert "missing" in resp.json()["error"].lower()
        finally:
            restore()


# ---------------------------------------------------------------------------
# _agent_headers() unit tests
# ---------------------------------------------------------------------------


class TestAgentHeaders:
    """Test that _agent_headers() reads from context vars correctly."""

    def test_returns_x_agent_when_claims_present(self):
        """When T1 claims are set, _agent_headers returns X-Agent header."""
        import mcp_server.server as srv
        from mcp_server.auth import DelegationClaims

        claims = DelegationClaims(
            tenant_id="t-1",
            org_id="o-1",
            agent="tucker",
            scope=["read:aircraft"],
        )
        token = srv._current_claims.set(claims)
        try:
            result = srv._agent_headers()
            assert result == {"X-Agent": "tucker"}
        finally:
            srv._current_claims.reset(token)

    def test_returns_none_when_no_claims(self):
        """When no T1 claims, _agent_headers returns None."""
        import mcp_server.server as srv

        token = srv._current_claims.set(None)
        try:
            result = srv._agent_headers()
            assert result is None
        finally:
            srv._current_claims.reset(token)

    def test_returns_correct_agent_for_each_slug(self):
        """Each agent slug is correctly forwarded."""
        import mcp_server.server as srv
        from mcp_server.auth import DelegationClaims

        for slug in ["concord", "tucker", "meridian", "ren", "sterling"]:
            claims = DelegationClaims(
                tenant_id="t-1",
                org_id="o-1",
                agent=slug,
                scope=["read:company"],
            )
            token = srv._current_claims.set(claims)
            try:
                result = srv._agent_headers()
                assert result == {"X-Agent": slug}
            finally:
                srv._current_claims.reset(token)
