"""Tests for MCP Gateway JWT validation and tenant database.

Tests the T1 JWT validation with K3 (public key) and the SQLite
tenant_id -> K4 lookup.
See AUTH_DECISION.md for the full key/token reference.
"""

import os
import tempfile
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_server.auth import (
    DelegationClaims,
    load_public_key,
    validate_delegation_token,
)
from mcp_server.tenant_db import (
    add_tenant,
    get_tenant_token,
    list_tenants,
    remove_tenant,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def key_pair():
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
    """Generate a different RS256 key pair (for rejection tests)."""
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
def tenant_db(tmp_path, monkeypatch):
    """Use a temp SQLite DB for tenant tests."""
    db_path = str(tmp_path / "test_tenants.db")
    monkeypatch.setattr("mcp_server.tenant_db._DB_PATH", db_path)
    return db_path


def _mint_t1(
    private_pem: bytes,
    tenant_id: str = "tenant-1",
    org_id: str = "org-1",
    agent_slug: str = "tucker",
    scope: list[str] | None = None,  # None = use default, [] = empty
    max_tier: str = "read_only",
    exp_minutes: int = 30,
    issuer: str = "https://api.uavcrew.ai",
    audience: str = "mcp-gateway",
) -> str:
    """Helper: mint a T1 JWT for testing (simulates UAVCrew side)."""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "sub": f"agent:{agent_slug}",
        "aud": audience,
        "tenant_id": tenant_id,
        "org_id": org_id,
        "session_id": "test-session",
        "scope": ["read:aircraft", "read:maintenance"] if scope is None else scope,
        "max_tier": max_tier,
        "exp": now + timedelta(minutes=exp_minutes),
        "iat": now,
        "jti": "inv_test123",
    }
    return pyjwt.encode(payload, private_pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# Tests: load_public_key
# ---------------------------------------------------------------------------


class TestLoadPublicKey:
    def test_returns_none_for_empty_path(self):
        assert load_public_key("") is None

    def test_returns_none_for_missing_file(self):
        assert load_public_key("/nonexistent/key.pem") is None

    def test_loads_valid_key(self, key_pair, tmp_path):
        _, public_pem = key_pair
        path = tmp_path / "k3.pem"
        path.write_bytes(public_pem)
        result = load_public_key(str(path))
        assert result == public_pem


# ---------------------------------------------------------------------------
# Tests: validate_delegation_token
# ---------------------------------------------------------------------------


class TestValidateDelegationToken:
    def test_valid_token(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem)
        claims = validate_delegation_token(token, public_pem)

        assert claims is not None
        assert claims.tenant_id == "tenant-1"
        assert claims.org_id == "org-1"
        assert claims.agent == "tucker"
        assert claims.scope == ["read:aircraft", "read:maintenance"]
        assert claims.max_tier == "read_only"
        assert claims.session_id == "test-session"
        assert claims.jti == "inv_test123"

    def test_expired_token(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem, exp_minutes=-1)  # Already expired
        claims = validate_delegation_token(token, public_pem)
        assert claims is None

    def test_wrong_key_rejected(self, key_pair, wrong_key_pair):
        private_pem, _ = key_pair
        _, wrong_public = wrong_key_pair
        token = _mint_t1(private_pem)
        claims = validate_delegation_token(token, wrong_public)
        assert claims is None

    def test_wrong_issuer_rejected(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem, issuer="https://evil.com")
        claims = validate_delegation_token(token, public_pem)
        assert claims is None

    def test_wrong_audience_rejected(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem, audience="wrong-audience")
        claims = validate_delegation_token(token, public_pem)
        assert claims is None

    def test_missing_tenant_id_rejected(self, key_pair):
        private_pem, public_pem = key_pair
        # Mint a token without tenant_id
        now = datetime.now(timezone.utc)
        payload = {
            "iss": "https://api.uavcrew.ai",
            "sub": "agent:tucker",
            "aud": "mcp-gateway",
            "org_id": "org-1",
            "scope": ["read:aircraft"],
            "exp": now + timedelta(minutes=30),
            "iat": now,
        }
        token = pyjwt.encode(payload, private_pem, algorithm="RS256")
        claims = validate_delegation_token(token, public_pem)
        assert claims is None

    def test_agent_extracted_from_sub(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem, agent_slug="sterling")
        claims = validate_delegation_token(token, public_pem)
        assert claims.agent == "sterling"

    def test_garbage_token_rejected(self, key_pair):
        _, public_pem = key_pair
        claims = validate_delegation_token("not.a.jwt", public_pem)
        assert claims is None

    def test_empty_scope_allowed(self, key_pair):
        private_pem, public_pem = key_pair
        token = _mint_t1(private_pem, scope=[])
        claims = validate_delegation_token(token, public_pem)
        assert claims is not None
        assert claims.scope == []

    def test_defaults_for_optional_fields(self, key_pair):
        private_pem, public_pem = key_pair
        # Mint a minimal token (only required fields)
        now = datetime.now(timezone.utc)
        payload = {
            "iss": "https://api.uavcrew.ai",
            "sub": "agent:meridian",
            "aud": "mcp-gateway",
            "tenant_id": "t-1",
            "exp": now + timedelta(minutes=30),
            "iat": now,
        }
        token = pyjwt.encode(payload, private_pem, algorithm="RS256")
        claims = validate_delegation_token(token, public_pem)
        assert claims is not None
        assert claims.org_id == ""
        assert claims.scope == []
        assert claims.max_tier == "read_only"
        assert claims.session_id == ""
        assert claims.jti == ""


# ---------------------------------------------------------------------------
# Tests: tenant_db
# ---------------------------------------------------------------------------


class TestTenantDB:
    def test_get_nonexistent_tenant(self, tenant_db):
        assert get_tenant_token("nonexistent") is None

    def test_add_and_get_tenant(self, tenant_db):
        add_tenant("t-1", "api_token_123", "Test Tenant")
        token = get_tenant_token("t-1")
        assert token == "api_token_123"

    def test_add_tenant_upsert(self, tenant_db):
        add_tenant("t-1", "old_token")
        add_tenant("t-1", "new_token")  # Should update
        assert get_tenant_token("t-1") == "new_token"

    def test_remove_tenant(self, tenant_db):
        add_tenant("t-1", "token")
        assert remove_tenant("t-1") is True
        assert get_tenant_token("t-1") is None

    def test_remove_nonexistent_tenant(self, tenant_db):
        assert remove_tenant("nonexistent") is False

    def test_list_tenants(self, tenant_db):
        add_tenant("t-1", "token-1", "Alpha")
        add_tenant("t-2", "token-2", "Beta")
        tenants = list_tenants()
        assert len(tenants) == 2
        ids = {t["tenant_id"] for t in tenants}
        assert ids == {"t-1", "t-2"}
        # Tokens should NOT be in the listing
        for t in tenants:
            assert "api_token" not in t

    def test_list_empty(self, tenant_db):
        assert list_tenants() == []

    def test_multiple_tenants_isolated(self, tenant_db):
        add_tenant("t-alpha", "token-alpha", "Alpha Inc")
        add_tenant("t-beta", "token-beta", "Beta Corp")
        assert get_tenant_token("t-alpha") == "token-alpha"
        assert get_tenant_token("t-beta") == "token-beta"
        # Remove one, other stays
        remove_tenant("t-alpha")
        assert get_tenant_token("t-alpha") is None
        assert get_tenant_token("t-beta") == "token-beta"
