"""UAVCrew MCP Gateway v2.0.

MCP server that translates entity-level operations into client API calls.
Uses the official MCP Python SDK (FastMCP) with Streamable HTTP transport.

Architecture:
  Agent → MCP Gateway → Client API (AYNA Comply, etc.)

Authentication:
  T1 JWT: UAVCrew mints T1 signed with K2. Gateway validates with K3.
  See AUTH_DECISION.md for the full key/token reference.

Tools (4 generic + 16 dedicated):
  get_entity     - Get a single entity record by ID
  list_entities  - List entity records with filtering and pagination
  search         - Search across one or all entity types
  action         - Execute a write action on an entity (create, update, start, etc.)

  Rule tools (7):
  rule_read, rule_coverage, rule_add_child, rule_update, rule_delete,
  rule_link_task, rule_unlink_task

  Checklist tools (9):
  checklist_read, checklist_list, checklist_create, checklist_update,
  checklist_add_checkbox, checklist_add_system_check, checklist_add_log_entry,
  checklist_update_task, checklist_remove_task

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
_api_base_url = (
    os.environ.get("CLIENT_API_BASE_URL", "").strip() or _manifest["api_base_url"]
)
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
_current_token: ContextVar[str | None] = ContextVar("token", default=None)  # K4
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


def _agent_headers() -> dict[str, str] | None:
    """Build X-Agent header from current claims, if available."""
    claims = _get_claims()
    if claims and claims.agent:
        return {"X-Agent": claims.agent}
    return None


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
        path = f"{entity_def['path'].rstrip('/')}/{id}"

    return await _api_client.get(path, token, extra_headers=_agent_headers())


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
    return await _api_client.get(
        path, token, query=query, extra_headers=_agent_headers()
    )


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
    headers = _agent_headers()
    if entity:
        search_params = {"search": query}
        entity_def = get_entity(_manifest, entity)
        path = entity_def["path"]
        return await _api_client.get(
            path, token, query=search_params, extra_headers=headers
        )
    else:
        # Unified search across all entities
        return await _api_client.get(
            "/search", token, query={"q": query}, extra_headers=headers
        )


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
    return await _api_client.request(
        method, path, token, params=params, extra_headers=_agent_headers()
    )


# ---------------------------------------------------------------------------
# Rule tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def rule_read(rule_id: str) -> dict[str, Any]:
    """Read a rule with its policy text, child rules, and per-child linked tasks.

    Use this before creating child rules to check what already exists.
    Also use it to get the rule's section_number and description (policy text).

    Args:
        rule_id: UUID of the rule to read.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.get(
        f"/rules/{rule_id}/", token, extra_headers=_agent_headers()
    )


@mcp.tool()
async def rule_coverage(rule_id: str) -> dict[str, Any]:
    """Get all checklist tasks currently satisfying a rule.

    Returns direct_tasks (linked to the rule itself) and child_rule_coverage
    (one entry per child rule with its linked tasks and is_covered flag).
    Always call this before making changes to avoid duplicating links.

    Args:
        rule_id: UUID of the rule.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.get(
        f"/rules/{rule_id}/coverage/", token, extra_headers=_agent_headers()
    )


@mcp.tool()
async def rule_add_child(
    parent_rule_id: str, title: str, text: str = ""
) -> dict[str, Any]:
    """Add a child rule under a parent rule.

    Section number is assigned automatically (e.g. parent '1' → children '1.1', '1.2', ...).
    Only works on organization rules — FAA and manufacturer rules are read-only.
    Returns the created child rule including its id and section_number.

    Args:
        parent_rule_id: UUID of the parent rule.
        title: Short name for this obligation (e.g. 'Pilot currency verification').
        text: Full policy text for this specific obligation. Sent as 'description' to the API.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.post(
        f"/rules/{parent_rule_id}/sub-rules/",
        token,
        params={"title": title, "description": text},
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def rule_update(
    rule_id: str,
    title: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """Update a rule's title or policy text.

    Works for both parent and child rules. At least one of title or text must be provided.

    Args:
        rule_id: UUID of the rule to update.
        title: New title (omit to leave unchanged).
        text: New policy text — sent as 'description' to the API (omit to leave unchanged).
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if text is not None:
        body["description"] = text
    if not body:
        return {"success": False, "error": "Provide at least one of title or text."}
    return await _api_client.patch(
        f"/rules/sub-rules/{rule_id}/",
        token,
        params=body,
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def rule_delete(rule_id: str) -> dict[str, Any]:
    """Delete a child rule (soft-delete).

    The rule will no longer appear in the UI or API responses.
    Only use on child rules — do not delete top-level rules.

    Args:
        rule_id: UUID of the child rule to delete.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.request(
        "DELETE", f"/rules/sub-rules/{rule_id}/", token, extra_headers=_agent_headers()
    )


@mcp.tool()
async def rule_link_task(
    rule_id: str, checklist_id: str, task_id: str
) -> dict[str, Any]:
    """Link a checklist task to a rule, marking it as what operationally enforces that rule.

    A task can be linked to multiple rules simultaneously.
    After linking, the task appears in rule_coverage under this rule.

    Args:
        rule_id: UUID of the rule (or child rule) to link to.
        checklist_id: UUID of the checklist that contains the task.
        task_id: The task item ID within the checklist (from checklist_read or checklist_add_* response).
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.post(
        f"/rules/sub-rules/{rule_id}/enforce/",
        token,
        params={"checklist_id": checklist_id, "task_id": task_id},
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def rule_unlink_task(
    rule_id: str, checklist_id: str, task_id: str
) -> dict[str, Any]:
    """Remove the link between a checklist task and a rule.

    Args:
        rule_id: UUID of the rule to unlink from.
        checklist_id: UUID of the checklist containing the task.
        task_id: The task item ID to unlink.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.request(
        "DELETE",
        f"/rules/sub-rules/{rule_id}/enforce/",
        token,
        params={"checklist_id": checklist_id, "task_id": task_id},
        extra_headers=_agent_headers(),
    )


# ---------------------------------------------------------------------------
# Checklist tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def checklist_read(checklist_id: str) -> dict[str, Any]:
    """Read a checklist and all its tasks.

    Every task in the response includes a task_id — use it in rule_link_task.
    Also returns context_tag, entity_type, and auto_attach configuration.

    Args:
        checklist_id: UUID of the checklist to read.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.get(
        f"/checklists/templates/{checklist_id}", token, extra_headers=_agent_headers()
    )


@mcp.tool()
async def checklist_list(
    entity_type: str | None = None,
    context_tag: str | None = None,
) -> dict[str, Any]:
    """List checklists for the organization, optionally filtered.

    Args:
        entity_type: Filter by what the checklist applies to — aircraft, pilot, flight, mission, maintenance.
        context_tag: Filter by when it runs — pre_flight, post_flight, emergency, onboarding.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    query: dict[str, str] = {}
    if entity_type:
        query["entity_type"] = entity_type
    if context_tag:
        query["context_tag"] = context_tag
    return await _api_client.get(
        "/checklists/templates",
        token,
        query=query or None,
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def checklist_create(
    title: str, entity_type: str, context_tag: str
) -> dict[str, Any]:
    """Create a new empty checklist. Add tasks to it using checklist_add_* tools.

    Args:
        title: Human-readable name (e.g. 'Pre-Flight Hardware Check').
        entity_type: What this checklist applies to — aircraft, pilot, flight, mission, maintenance.
        context_tag: When it runs — pre_flight, post_flight, emergency, onboarding.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.post(
        "/checklists/templates/",
        token,
        params={
            "title": title,
            "applies_to_entity_types": [entity_type],
            "context_tag": context_tag,
        },
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def checklist_update(
    checklist_id: str,
    title: str | None = None,
    context_tag: str | None = None,
) -> dict[str, Any]:
    """Update a checklist's title or context tag.

    Args:
        checklist_id: UUID of the checklist to update.
        title: New title (omit to leave unchanged).
        context_tag: New context tag (omit to leave unchanged).
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if context_tag is not None:
        body["context_tag"] = context_tag
    if not body:
        return {
            "success": False,
            "error": "Provide at least one of title or context_tag.",
        }
    return await _api_client.patch(
        f"/checklists/templates/{checklist_id}",
        token,
        params=body,
        extra_headers=_agent_headers(),
    )


async def _add_checklist_task(
    checklist_id: str,
    text: str,
    source: str,
    required: bool = True,
    is_critical: bool = False,
) -> dict[str, Any]:
    """Shared implementation for all checklist_add_* tools."""
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.post(
        f"/checklists/templates/{checklist_id}/items/",
        token,
        params={
            "text": text,
            "source": source,
            "required": required,
            "is_critical": is_critical,
        },
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def checklist_add_checkbox(
    checklist_id: str,
    text: str,
    required: bool = True,
    is_critical: bool = False,
) -> dict[str, Any]:
    """Add a manual task to a checklist. The user physically checks this off during an operation.

    Use for physical actions: verify battery charge, inspect propellers, confirm weather brief.
    Returns task_id — use it directly in rule_link_task without re-reading the checklist.

    Args:
        checklist_id: UUID of the checklist to add to.
        text: Task description (e.g. 'Verify battery charge above 80%').
        required: Must be completed to submit the checklist (default: true).
        is_critical: Blocks the operation if not completed (default: false).
    """
    return await _add_checklist_task(
        checklist_id, text, "manual", required, is_critical
    )


@mcp.tool()
async def checklist_add_system_check(
    checklist_id: str,
    text: str,
    required: bool = True,
    is_critical: bool = False,
) -> dict[str, Any]:
    """Add a system-resolved task to a checklist. Ayna auto-checks this from its data.

    Only use when Ayna can genuinely resolve it: pilot cert expiry, drone registration,
    Remote ID status. System checks that cannot be auto-resolved will always show as failing.
    Returns task_id — use it directly in rule_link_task.

    Args:
        checklist_id: UUID of the checklist to add to.
        text: Check description (e.g. 'Pilot Part 107 certificate is current').
        required: Default true.
        is_critical: Default false.
    """
    return await _add_checklist_task(
        checklist_id, text, "checker", required, is_critical
    )


@mcp.tool()
async def checklist_add_log_entry(
    checklist_id: str,
    text: str,
    required: bool = True,
    is_critical: bool = False,
) -> dict[str, Any]:
    """Add a record task to a checklist. Completing this requires attaching a document or log entry.

    Use for documented actions: inspection reports, maintenance logs, flight briefs.
    Returns task_id — use it directly in rule_link_task.

    Args:
        checklist_id: UUID of the checklist to add to.
        text: Record description (e.g. 'Pre-flight hardware inspection report attached').
        required: Default true.
        is_critical: Default false.
    """
    return await _add_checklist_task(
        checklist_id, text, "record", required, is_critical
    )


@mcp.tool()
async def checklist_update_task(
    checklist_id: str,
    task_id: str,
    text: str | None = None,
    required: bool | None = None,
    is_critical: bool | None = None,
) -> dict[str, Any]:
    """Update a task item's text or flags. Does not change the task type.

    Args:
        checklist_id: UUID of the checklist containing the task.
        task_id: The task item ID to update.
        text: New task text (omit to leave unchanged).
        required: New required flag (omit to leave unchanged).
        is_critical: New critical flag (omit to leave unchanged).
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    body: dict[str, Any] = {}
    if text is not None:
        body["text"] = text
    if required is not None:
        body["required"] = required
    if is_critical is not None:
        body["is_critical"] = is_critical
    if not body:
        return {"success": False, "error": "Provide at least one field to update."}
    return await _api_client.patch(
        f"/checklists/templates/{checklist_id}/items/{task_id}/",
        token,
        params=body,
        extra_headers=_agent_headers(),
    )


@mcp.tool()
async def checklist_remove_task(checklist_id: str, task_id: str) -> dict[str, Any]:
    """Remove a task from a checklist.

    Args:
        checklist_id: UUID of the checklist containing the task.
        task_id: The task item ID to remove.
    """
    token = _resolve_token()
    if not token:
        return {"success": False, "error": "No API token available."}
    return await _api_client.request(
        "DELETE",
        f"/checklists/templates/{checklist_id}/items/{task_id}/",
        token,
        extra_headers=_agent_headers(),
    )


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token: T1 JWT using K3.

    T1 JWT path: validates with K3, extracts tenant_id, looks up K4.
    No auth configured: allows all requests (development mode).
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

        # No auth configured — development mode
        if not _public_key:
            result = await _resolver.resolve()
            _current_token.set(result.token)
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

        # T1 JWT validation
        if token.count(".") == 2:
            claims = validate_delegation_token(token, _public_key)
            if claims:
                result = await _resolver.resolve(claims.tenant_id, token)
                if not result.ok:
                    resolver_url = getattr(_resolver, "resolver_url", None)
                    logger.warning(
                        "K4 resolution failed for tenant %s: reason=%s, "
                        "resolver_url=%s, agent=%s, jti=%s",
                        claims.tenant_id,
                        result.reason,
                        resolver_url,
                        claims.agent,
                        claims.jti,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": f"K4 resolution failed for tenant"
                            f" '{claims.tenant_id}'",
                            "reason": result.reason,
                        },
                    )
                _current_claims.set(claims)
                _current_token.set(result.token)
                _current_t1_jwt.set(token)
                try:
                    return await call_next(request)
                finally:
                    _current_claims.set(None)
                    _current_token.set(None)
                    _current_t1_jwt.set(None)

        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or expired T1 token"},
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
    auth_mode = "jwt" if _public_key else "none"
    token_mode = _manifest.get("auth", {}).get("mode", "static")
    resolver_url = getattr(_resolver, "resolver_url", None)
    return {
        "status": "healthy",
        "service": "mcp-gateway",
        "version": __version__,
        "entities": entity_count,
        "auth_mode": auth_mode,
        "token_resolution": token_mode,
        "resolver_url": resolver_url,
    }


app.mount("/", mcp_app)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _print_banner(host: str, port: int):
    """Print startup banner."""
    entity_names = get_entity_names(_manifest)
    auth_mode = "JWT (K3)" if _public_key else "none (dev mode)"
    token_mode = _manifest.get("auth", {}).get("mode", "static")
    resolver_url = getattr(_resolver, "resolver_url", None)
    print(f"\nStarting UAVCrew MCP Gateway v{__version__} on {host}:{port}")
    print(f"  MCP endpoint:  POST http://{host}:{port}/mcp")
    print(f"  Health check:  GET  http://{host}:{port}/health")
    print(f"  Auth mode:     {auth_mode}")
    print(f"  Token resolve: {token_mode}")
    if resolver_url:
        print(f"  Resolver URL:  {resolver_url}")
    print(f"  Entities ({len(entity_names)}): {', '.join(entity_names)}")
    print("  Tools (4): get_entity, list_entities, search, action\n")


def main():
    """Run the MCP Gateway via gunicorn (production)."""
    import sys
    from pathlib import Path

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8400"))

    _print_banner(host, port)

    # Locate gunicorn config: check working directory, then package root
    config_path = Path("gunicorn_config.py")
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / "gunicorn_config.py"

    args = [
        "gunicorn",
        "--bind",
        f"{host}:{port}",
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
    port = int(os.environ.get("MCP_PORT", "8400"))

    _print_banner(host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    dev()
