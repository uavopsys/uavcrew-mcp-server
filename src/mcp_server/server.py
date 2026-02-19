"""UAVCrew MCP Gateway v2.0.

MCP server that translates entity-level operations into client API calls.
Uses the official MCP Python SDK (FastMCP) with Streamable HTTP transport.

Architecture:
  Agent → MCP Gateway → Client API (AYNA Comply, etc.)

Authentication:
  T1 JWT (new): UAVCrew mints T1 signed with K2. Gateway validates with K3.
  Static API key (legacy): MCP_API_KEY env var. Kept for backward compat.
  See AUTH_DECISION.md for the full key/token reference.

Tools (4):
  get_entity     - Get a single entity record by ID
  list_entities  - List entity records with filtering and pagination
  search         - Search across one or all entity types
  action         - Execute a write action on an entity (create, update, start, etc.)

Resource (1):
  entities://manifest - Entity definitions, paths, and available actions
"""

import json
import logging
import os
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from fastmcp import FastMCP

from . import __version__
from .api_client import ApiClient
from .auth import DelegationClaims, load_public_key, validate_delegation_token
from .manifest import load_manifest, get_entity, get_entity_names, get_entity_actions
from .token_resolver import TokenResolver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load manifest
# ---------------------------------------------------------------------------

_manifest = load_manifest()
_api_base_url = os.environ.get("CLIENT_API_BASE_URL", "").strip() or _manifest["api_base_url"]
_api_client = ApiClient(_api_base_url)
_resolver = TokenResolver(_manifest.get("auth", {}), _api_base_url)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP(name="uavcrew-mcp-server")

# ---------------------------------------------------------------------------
# Auth context (threaded through to tools via contextvars)
# ---------------------------------------------------------------------------

_current_claims: ContextVar[DelegationClaims | None] = ContextVar(
    "claims", default=None
)
_current_token: ContextVar[str | None] = ContextVar(
    "token", default=None
)  # K4
_current_t1_jwt: ContextVar[str | None] = ContextVar(
    "t1_jwt", default=None
)  # Raw T1 JWT for dynamic resolver

# Load K3 at startup (if configured)
_public_key = load_public_key(os.environ.get("MCP_JWT_PUBLIC_KEY_PATH", ""))


def _resolve_token() -> str | None:
    """Get the resolved K4 token for the current request.

    Set by AuthMiddleware after resolving via TokenResolver.
    """
    return _current_token.get(None)


def _get_claims() -> DelegationClaims | None:
    """Get validated T1 claims for the current request."""
    return _current_claims.get(None)


def _check_scope(entity: str, operation: str = "read") -> dict | None:
    """Check if the current agent is authorized for an entity operation.

    Returns None if authorized, or an error dict if not.
    Only enforced when T1 claims are present (legacy mode skips scope checks).
    """
    claims = _get_claims()
    if claims is None:
        # Legacy mode — no scope enforcement
        return None

    required_scope = f"{operation}:{entity}"
    if required_scope not in claims.scope:
        return {
            "success": False,
            "error": f"Agent '{claims.agent}' not authorized for '{required_scope}'.",
        }
    return None


# ---------------------------------------------------------------------------
# Resource: entities://manifest
# ---------------------------------------------------------------------------

@mcp.resource(
    "entities://manifest",
    name="Entity Manifest",
    description="Entity definitions, API paths, and available actions. Read this first to discover what entities exist and what operations are available.",
    mime_type="application/json",
)
def manifest_resource() -> str:
    """Return the full manifest for agent discovery."""
    return json.dumps(_manifest, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_entity
# ---------------------------------------------------------------------------

@mcp.tool(name="get_entity")
async def get_entity_fn(entity: str, id: str | None = None) -> dict[str, Any]:
    """Get a single entity record by ID, or the singleton record for entities without IDs.

    Args:
        entity: Entity type (e.g., "pilot", "aircraft", "company").
        id: Entity ID. Required for most entities, omit for singletons (e.g., company).
    """
    entity_def = get_entity(_manifest, entity)
    if entity_def is None:
        available = ", ".join(get_entity_names(_manifest))
        return {
            "available": False,
            "entity": entity,
            "message": f"Entity '{entity}' not configured. Available: {available}",
        }

    if not entity_def.get("read", False):
        return {
            "available": False,
            "entity": entity,
            "message": f"Read not available for '{entity}'.",
        }

    scope_error = _check_scope(entity, "read")
    if scope_error:
        return scope_error

    token = _resolve_token()
    if not token:
        return {
            "success": False,
            "error": "No API token available for this tenant.",
        }

    # Singleton entities (id_field is null) — GET path directly, no id suffix
    if entity_def.get("id_field") is None:
        path = entity_def["path"]
    else:
        if not id:
            return {
                "success": False,
                "error": f"Entity '{entity}' requires an id parameter.",
            }
        path = f"{entity_def['path']}/{id}"

    return await _api_client.get(path, token)


# ---------------------------------------------------------------------------
# Tool: list_entities
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_entities(
    entity: str,
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List entity records with optional filtering and pagination.

    Args:
        entity: Entity type (e.g., "pilot", "aircraft", "mission").
        filters: Optional key-value filters (e.g., {"status": "active"}).
        sort: Optional sort field (e.g., "created_at", "-name" for descending).
        limit: Maximum records to return (default 50).
        offset: Number of records to skip for pagination.
    """
    entity_def = get_entity(_manifest, entity)
    if entity_def is None:
        available = ", ".join(get_entity_names(_manifest))
        return {
            "available": False,
            "entity": entity,
            "message": f"Entity '{entity}' not configured. Available: {available}",
        }

    if not entity_def.get("read", False):
        return {
            "available": False,
            "entity": entity,
            "message": f"Read not available for '{entity}'.",
        }

    scope_error = _check_scope(entity, "read")
    if scope_error:
        return scope_error

    token = _resolve_token()
    if not token:
        return {
            "success": False,
            "error": "No API token available for this tenant.",
        }

    # Build query parameters
    query: dict[str, Any] = {"limit": limit, "offset": offset}
    if filters:
        query.update(filters)
    if sort:
        query["sort"] = sort

    path = entity_def["path"]
    return await _api_client.get(path, token, query=query)


# ---------------------------------------------------------------------------
# Tool: search
# ---------------------------------------------------------------------------

@mcp.tool()
async def search(
    query: str,
    entity: str | None = None,
) -> dict[str, Any]:
    """Search across one or all entity types.

    Args:
        query: Search query string.
        entity: Optional entity type to scope search. If omitted, searches all.
    """
    if entity is not None:
        entity_def = get_entity(_manifest, entity)
        if entity_def is None:
            available = ", ".join(get_entity_names(_manifest))
            return {
                "available": False,
                "entity": entity,
                "message": f"Entity '{entity}' not configured. Available: {available}",
            }
        if not entity_def.get("search", False):
            return {
                "available": False,
                "entity": entity,
                "message": f"Search not available for '{entity}'.",
            }
        scope_error = _check_scope(entity, "read")
        if scope_error:
            return scope_error

    token = _resolve_token()
    if not token:
        return {
            "success": False,
            "error": "No API token available for this tenant.",
        }

    # Use unified search endpoint if available, else per-entity search
    if entity:
        search_params = {"search": query}
        entity_def = get_entity(_manifest, entity)
        path = entity_def["path"]
        return await _api_client.get(path, token, query=search_params)
    else:
        # Unified search across all entities
        return await _api_client.get("/search", token, query={"q": query})


# ---------------------------------------------------------------------------
# Tool: action
# ---------------------------------------------------------------------------

@mcp.tool()
async def action(
    entity: str,
    action: str,
    id: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a write action on an entity.

    Actions are entity-specific operations like create, update, start, complete.
    Read the entities://manifest resource to discover available actions per entity.

    Args:
        entity: Entity type (e.g., "pilot", "aircraft", "mission").
        action: Action name (e.g., "create", "update", "start", "complete").
        id: Entity ID (required for actions that target a specific record).
        params: Action parameters as key-value pairs.
    """
    entity_def = get_entity(_manifest, entity)
    if entity_def is None:
        available = ", ".join(get_entity_names(_manifest))
        return {
            "available": False,
            "entity": entity,
            "message": f"Entity '{entity}' not configured. Available: {available}",
        }

    actions = get_entity_actions(_manifest, entity)
    if not actions:
        return {
            "available": False,
            "entity": entity,
            "message": f"No actions available for '{entity}'. This entity is read-only.",
        }

    action_def = actions.get(action)
    if action_def is None:
        available_actions = ", ".join(actions.keys())
        return {
            "available": False,
            "entity": entity,
            "action": action,
            "message": f"Action '{action}' not available for '{entity}'. Available: {available_actions}",
        }

    # Check write scope
    scope_error = _check_scope(entity, "write")
    if scope_error:
        return scope_error

    token = _resolve_token()
    if not token:
        return {
            "success": False,
            "error": "No API token available for this tenant.",
        }

    # Build the path, substituting {id} placeholder
    path = action_def["path"]
    if "{id}" in path:
        if id is None:
            return {
                "success": False,
                "error": f"Action '{action}' on '{entity}' requires an id parameter.",
            }
        path = path.replace("{id}", id)

    method = action_def["method"]
    return await _api_client.request(method, path, token, params=params)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def _load_api_keys() -> set[str]:
    """Load configured MCP API keys from environment (legacy auth)."""
    keys = set()

    single_key = os.environ.get("MCP_API_KEY", "").strip()
    if single_key:
        keys.add(single_key)

    multi_keys = os.environ.get("MCP_API_KEYS", "").strip()
    if multi_keys:
        for key in multi_keys.split(","):
            key = key.strip()
            if key:
                keys.add(key)

    return keys


_legacy_api_keys = _load_api_keys()


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token: T1 JWT (new) or static API key (legacy).

    T1 JWT path: validates with K3, extracts tenant_id, looks up K4.
    Legacy path: checks against MCP_API_KEY env var, uses CLIENT_API_TOKEN.
    No auth configured: allows all requests (development mode).
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

        # No auth configured at all — development mode
        if not _public_key and not _legacy_api_keys:
            k4 = await _resolver.resolve()
            _current_token.set(k4)
            _current_claims.set(None)
            _current_t1_jwt.set(None)
            try:
                return await call_next(request)
            finally:
                _current_token.set(None)

        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing authorization"},
            )

        # Try T1 JWT first (if K3 is configured and token looks like a JWT)
        if _public_key and token.count(".") == 2:
            claims = validate_delegation_token(token, _public_key)
            if claims:
                # Resolve K4 for this tenant (static or dynamic)
                k4 = await _resolver.resolve(claims.tenant_id, token)
                if not k4:
                    logger.warning(
                        "No K4 for tenant %s (agent=%s, jti=%s)",
                        claims.tenant_id,
                        claims.agent,
                        claims.jti,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": f"No API token for tenant"
                            f" '{claims.tenant_id}'"
                        },
                    )
                _current_claims.set(claims)
                _current_token.set(k4)
                _current_t1_jwt.set(token)
                try:
                    return await call_next(request)
                finally:
                    _current_claims.set(None)
                    _current_token.set(None)
                    _current_t1_jwt.set(None)
            else:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid or expired T1 token"},
                )

        # Legacy: static API key check
        if _legacy_api_keys and token in _legacy_api_keys:
            k4 = await _resolver.resolve()
            _current_token.set(k4)
            _current_claims.set(None)
            _current_t1_jwt.set(None)
            try:
                return await call_next(request)
            finally:
                _current_token.set(None)

        return JSONResponse(
            status_code=401,
            content={"error": "Invalid credentials"},
        )


# ---------------------------------------------------------------------------
# FastAPI app with MCP mounted
# ---------------------------------------------------------------------------

mcp_app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)

app = FastAPI(
    title="UAVCrew MCP Gateway",
    description="MCP Gateway for UAVCrew AI agent access to client data",
    version=__version__,
    lifespan=mcp_app.lifespan,
)

app.add_middleware(AuthMiddleware)


@app.get("/health")
async def health():
    """Health check endpoint."""
    entity_count = len(get_entity_names(_manifest))
    auth_mode = "jwt" if _public_key else ("api_key" if _legacy_api_keys else "none")
    token_mode = _manifest.get("auth", {}).get("mode", "static")
    return {
        "status": "healthy",
        "service": "mcp-gateway",
        "version": __version__,
        "entities": entity_count,
        "auth_mode": auth_mode,
        "token_resolution": token_mode,
    }


app.mount("/", mcp_app)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _print_banner(host: str, port: int):
    """Print startup banner."""
    entity_names = get_entity_names(_manifest)
    auth_mode = "JWT (K3)" if _public_key else (
        "API key (legacy)" if _legacy_api_keys else "none (dev mode)"
    )
    token_mode = _manifest.get("auth", {}).get("mode", "static")
    print(f"\nStarting UAVCrew MCP Gateway v{__version__} on {host}:{port}")
    print(f"  MCP endpoint:  POST http://{host}:{port}/mcp")
    print(f"  Health check:  GET  http://{host}:{port}/health")
    print(f"  Auth mode:     {auth_mode}")
    print(f"  Token resolve: {token_mode}")
    print(f"  Entities ({len(entity_names)}): {', '.join(entity_names)}")
    print(f"  Tools (4): get_entity, list_entities, search, action\n")


def main():
    """Run the MCP Gateway via gunicorn (production)."""
    import sys
    from pathlib import Path

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8200"))

    _print_banner(host, port)

    # Locate gunicorn config: check working directory, then package root
    config_path = Path("gunicorn_config.py")
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / "gunicorn_config.py"

    args = [
        "gunicorn",
        "--bind", f"{host}:{port}",
        "mcp_server.server:app",
    ]
    if config_path.exists():
        args.extend(["--config", str(config_path)])

    sys.argv = args

    from gunicorn.app.wsgiapp import WSGIApplication
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()


def dev():
    """Run the MCP Gateway via uvicorn (development)."""
    import uvicorn

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8200"))

    _print_banner(host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    dev()
