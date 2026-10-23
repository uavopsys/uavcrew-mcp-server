"""Aircraft comments route through the generic action tool and write scope."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from mcp_server import server
from mcp_server.auth import DelegationClaims
from mcp_server.manifest import load_manifest


@pytest.mark.parametrize("filename", ["manifest.json", "manifest.json.example"])
def test_manifest_has_aircraft_comment_action(filename):
    manifest = load_manifest(filename)
    action = manifest["entities"]["aircraft"]["actions"]["add_comment"]
    assert action["method"] == "POST"
    assert action["path"] == "/aircraft/{id}/comments"
    assert "content" in action["description"]
    assert "comment" not in manifest["entities"]


@pytest.mark.parametrize("allowed", [True, False])
def test_aircraft_comment_action(monkeypatch, allowed):
    request = AsyncMock(return_value={"success": True, "status_code": 201})
    monkeypatch.setattr(server._api_client, "request", request)
    claims = DelegationClaims(
        tenant_id="tenant-1", org_id="org-1", agent="sterling",
        scope=["write:aircraft"] if allowed else ["read:aircraft"],
    )
    claims_context = server._current_claims.set(claims)
    token_context = server._current_token.set("tenant-api-key")
    try:
        fn = getattr(server.action, "fn", server.action)
        result = asyncio.run(fn(
            entity="aircraft", action="add_comment", id="aircraft-uuid",
            params={"content": "Inspect propellers before next flight."},
        ))
        if allowed:
            assert result["success"] is True
            request.assert_awaited_once_with(
                "POST", "/aircraft/aircraft-uuid/comments", "tenant-api-key",
                params={"content": "Inspect propellers before next flight."},
                extra_headers={"X-Agent": "sterling"},
            )
        else:
            assert result["success"] is False
            assert "write:aircraft" in result["error"]
            request.assert_not_awaited()
    finally:
        server._current_token.reset(token_context)
        server._current_claims.reset(claims_context)
