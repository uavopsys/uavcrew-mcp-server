# Plan A: MCP Gateway v2.0

## Context

The UAVCrew MCP Gateway currently uses a hand-rolled JSON-RPC 2.0 implementation over FastAPI with manually maintained tool schemas and raw database tools. This plan replaces it with the official `mcp` Python SDK (`FastMCP`) and redesigns the tool surface around **entity-level operations** backed by client API endpoints.

**API-only architecture.** All data access goes through the client's REST API — no direct database queries. This follows the same pattern as Atlassian's MCP server (pure API translation). A database-read mode may be added in a future version for clients without an API.

---

## Architecture

```
UAVCrew Agent (CONCORD, TUCKER, etc.)
  ↓ UAVCrew mints T1 (signed JWT with tenant_id, scope, max_tier)
  ↓ Agent calls MCP tool with T1
MCP Gateway (on client infrastructure)
  ↓ validates T1 using K3 (public key)
  ↓ extracts tenant_id from T1 (cryptographic claim, not a parameter)
  ↓ looks up tenant_id in credential store → gets K4 (client API token)
  ↓ looks up entity in manifest → gets API path
  ↓ calls Client API with K4
Client API (AYNA Comply, etc.)
  ↓ validates K4 → resolves Organization → scopes data
  ↓ returns data for that organization only
MCP Gateway → Agent
```

The MCP server is an **entity adapter**: translates standardized entity operations into client-specific API calls using a manifest. The **credential store** maps `tenant_id → K4` so the gateway uses the right client API token for each tenant.

---

## Entities (12)

All entities support **read operations** (get, list, search) via generic MCP tools. Write operations are entity-specific **actions** declared in the manifest.

| # | Entity | Description |
|---|--------|-------------|
| 1 | `pilot` | Remote pilots, certifications, training, flight hours |
| 2 | `aircraft` | UAS/drones, registration, configuration, status |
| 3 | `flight` | Flight records, telemetry, duration |
| 4 | `mission` | Planned operations, assignments, status workflow |
| 5 | `maintenance` | Service records, inspections, scheduled work |
| 6 | `checklist` | Pre-flight, in-flight, post-flight checklists |
| 7 | `company` | Organization profile |
| 8 | `service` | Services offered or contracted |
| 9 | `product` | Products, equipment catalog |
| 10 | `artifact` | All files — certs, reports, logs, photos, deliverables |
| 11 | `crew` | Non-pilot personnel (observers, engineers, etc.) |
| 12 | `parts` | Batteries, propellers, sensors, payloads |

---

## Manifest (`manifest.json`)

One config file. Declares entities, their API paths, and available actions.

```json
{
  "api_base_url": "https://api.client.com/api/v1",
  "entities": {
    "pilot": {
      "path": "/pilots",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/pilots"
        },
        "update": {
          "method": "PATCH",
          "path": "/pilots/{id}"
        }
      }
    },
    "aircraft": {
      "path": "/drones",
      "id_field": "mavlink_id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/drones"
        },
        "update": {
          "method": "PATCH",
          "path": "/drones/{id}"
        }
      }
    },
    "flight": {
      "path": "/flights",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "start": {
          "method": "POST",
          "path": "/flights/start"
        },
        "end": {
          "method": "POST",
          "path": "/flights/{id}/end"
        },
        "cancel": {
          "method": "POST",
          "path": "/flights/{id}/cancel"
        }
      }
    },
    "mission": {
      "path": "/missions",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/missions"
        },
        "update": {
          "method": "PATCH",
          "path": "/missions/{id}"
        },
        "start": {
          "method": "POST",
          "path": "/missions/{id}/start"
        },
        "complete": {
          "method": "POST",
          "path": "/missions/{id}/complete"
        }
      }
    },
    "maintenance": {
      "path": "/maintenance",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/maintenance"
        },
        "update": {
          "method": "PATCH",
          "path": "/maintenance/{id}"
        },
        "start": {
          "method": "POST",
          "path": "/maintenance/{id}/start"
        },
        "complete": {
          "method": "POST",
          "path": "/maintenance/{id}/complete"
        }
      }
    },
    "checklist": {
      "path": "/checklists/templates",
      "id_field": "id",
      "read": true,
      "search": true
    },
    "company": {
      "path": "/organization",
      "id_field": null,
      "read": true,
      "search": false
    },
    "service": {
      "path": "/services",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/services"
        },
        "update": {
          "method": "PATCH",
          "path": "/services/{id}"
        }
      }
    },
    "product": {
      "path": "/products",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/products"
        },
        "update": {
          "method": "PATCH",
          "path": "/products/{id}"
        }
      }
    },
    "artifact": {
      "path": "/storage/files",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "upload": {
          "method": "POST",
          "path": "/storage/upload-url",
          "note": "Returns presigned upload URL, then register via POST /storage/files"
        },
        "update": {
          "method": "PATCH",
          "path": "/storage/files/{id}"
        },
        "move": {
          "method": "POST",
          "path": "/storage/files/{id}/move"
        },
        "get_download_url": {
          "method": "POST",
          "path": "/storage/files/{id}/download-url"
        }
      }
    },
    "crew": {
      "path": "/crew",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/crew"
        },
        "update": {
          "method": "PATCH",
          "path": "/crew/{id}"
        }
      }
    },
    "parts": {
      "path": "/parts",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": {
          "method": "POST",
          "path": "/parts"
        },
        "update": {
          "method": "PATCH",
          "path": "/parts/{id}"
        }
      }
    }
  }
}
```

### Manifest conventions

**Reads** (automatic from entity definition):
- `read: true` → `GET {path}/` (list) and `GET {path}/{id}` (get one)
- `search: true` → `GET {path}/?search={query}` or unified `/search/{entity_type}?q={query}`

**Actions** (write operations, per entity):
- Each action has a `method` and `path`
- `{id}` in path is replaced with the entity ID
- No actions key = read-only entity (checklist, company)
- Agent discovers available actions by reading the manifest resource

### How agents navigate

1. Agent reads `entities://manifest` resource
2. Sees all 12 entities with their read/search capabilities and available actions
3. For each entity, sees what actions (writes) are available
4. Agent calls read tools generically: `get_entity("aircraft", "MAV-001")`
5. Agent calls write tools by entity+action: `action("aircraft", "record_maintenance", id="MAV-001", params={...})`

Everything about an entity is in one place. Agents don't scan flat lists.

---

## MCP Surface

### Resource (1) — discovery

| URI | Type | Purpose |
|-----|------|---------|
| `entities://manifest` | Static | Full manifest: entities, paths, actions. Agent reads this first. |

### Read tools (3) — generic, work with any entity

| Tool | Signature | Purpose |
|------|-----------|---------|
| `get_entity` | `(entity, id)` | Get a single record by ID |
| `list_entities` | `(entity, filters?, sort?, limit=50, offset=0)` | List with filtering and pagination |
| `search` | `(query, entity?)` | Search within entity type or across all |

### Write tool (1) — routes to entity-specific actions

| Tool | Signature | Purpose |
|------|-----------|---------|
| `action` | `(entity, action, id?, params)` | Execute an entity action (create, update, start, etc.) |

Note: `tenant_id` is **not** a tool parameter. It is extracted from the validated T1 JWT by the auth middleware. Tools never receive it from the caller.

The `action` tool:
1. Looks up `entity` in manifest
2. Looks up `action` in that entity's `actions`
3. If not found → error: "Action 'X' not available for entity 'Y'. Available: create, update, ..."
4. Builds URL from action path, substituting `{id}`
5. Calls client API with the specified method and params as JSON body
6. Returns response

---

## Authentication Model

Full decision: `AUTH_DECISION.md` in the UAVCrew repo root.

### Keys & Tokens (reference labels)

| Label | What | Created by | Lives at |
|-------|------|-----------|----------|
| **K3** | JWT public key (RS256) | UAVCrew (derived from K2) | MCP Gateway config |
| **K4** | Per-tenant API token | Client (in their own system) | MCP Gateway credential store |
| **T1** | Delegation JWT (30-min, per invocation) | UAVCrew (signed with K2) | In-flight only |
| **T2** | Approval token (single-use, per write) | UAVCrew (signed with K2) | In-flight only |

K1 (chat API key) and K2 (JWT private key) live at UAVCrew — MCP Gateway never sees them.

### What MCP Gateway does

**On every tool call:**
1. Validate **T1** signature using **K3** (reject if invalid, expired, or wrong audience)
2. Extract `tenant_id` from **T1** (never accept it as a parameter)
3. Check `scope` claim in **T1** — reject if the requested entity is not in scope
4. Check `max_tier` claim in **T1** — reject if the operation exceeds the tier
5. Look up **K4** for `tenant_id` in credential store (reject if not found — fail closed)
6. Call Client API with **K4**

**For writes (T3+ actions):**
1. If `max_tier` in **T1** is `propose` → store proposal, return `proposal_id`, do NOT execute
2. Execution requires a separate **T2** (approval token) from UAVCrew
3. Validate **T2** signature using **K3**, match `proposal_id`, verify single-use
4. Then execute via Client API with **K4**

**Credential registration:**
- CLI: `uavcrew tenants add --tenant-id <id> --token <K4>`
- Stores `tenant_id → K4` mapping in local SQLite tenant DB
- MCP Gateway only serves tenants it has a **K4** for

### What the credential store does (AYNA-specific)

AYNA's API keys are scoped to one Organization. Each Organization (MMX Media, SkyOps, etc.) has its own API key (K4) that only returns data for that Organization. The credential store maps UAVCrew's `tenant_id` to the correct AYNA API key:

```
T1 arrives with tenant_id: "mmx-media-uuid"
  → credential store: "mmx-media-uuid" → K4 (ak_7f3a...)
    → AYNA auth: ak_7f3a... → Organization: MMX Media
      → AYNA queries: WHERE organization_id = <MMX Media UUID>
        → Returns only MMX Media's data
```

The credential store is **not** tenant management — UAVCrew manages tenants. It is credential registration: the client admin says "for this tenant_id, use this API token to call my API."

### Tool tiering (MCP Gateway enforces)

| Tier | What | Behavior |
|------|------|----------|
| T1: Read | get, list, search | Execute immediately |
| T2: Compute | reports, analysis | Execute immediately |
| T3: Propose | create, update | Queue as proposal, return proposal_id |
| T4: Execute | confirmed writes | Execute only with valid **T2** |
| T5: Critical | regulatory, grounding | Execute only with two **T2** tokens |

### Defense in depth (writes)

| Layer | Enforced by | How |
|-------|------------|-----|
| **T1 scope + max_tier** | MCP Gateway | Agent can only propose, not execute |
| **T2 approval token** | MCP Gateway | Write requires human approval (signed, single-use) |
| **Manifest actions** | MCP Gateway | Only actions declared in manifest are available |
| **K4 token scopes** | Client API | Client can issue read-only K4 tokens |
| **Client API logic** | Client API | Business rules — API validates and rejects |

### What replaces `MCP_API_KEY`

The static `MCP_API_KEY` shared secret is replaced by **T1** delegation JWTs. MCP Gateway validates using **K3** (public key). No static shared secret between UAVCrew and MCP Gateway.

---

## Implementation Steps

### Phase 1: Core Gateway (DONE)

#### 1. Create `src/mcp_server/server.py` ✓

FastMCP server with:
- FastMCP instance with `stateless_http=True`
- Manifest loading from `MCP_MANIFEST_PATH` or `./manifest.json`
- 1 resource (`entities://manifest`)
- 3 read tools + 1 action tool
- FastAPI wrapper with placeholder auth middleware + `/health` endpoint
- `main()` entry point running uvicorn

**Current auth:** `BearerAuthMiddleware` checks static `MCP_API_KEY` (placeholder for T1 JWT validation). `_resolve_token(org_id)` reads `CLIENT_API_TOKEN` env var (placeholder for credential store lookup).

#### 2. Create `src/mcp_server/manifest.py` ✓

Manifest loader and validator.

#### 3. Create `src/mcp_server/api_client.py` ✓

HTTP client for calling client APIs.

#### 4. Create `manifest.json.example` ✓

Reference manifest for AYNA Comply with all 12 entities and actions.

#### 5. Update `pyproject.toml` ✓

- Added `fastmcp>=2.0.0`, removed `sqlalchemy`, `boto3`, database drivers
- Entry points updated to `mcp_server.server:main`

#### 6. Update `requirements.txt` ✓

- `fastmcp>=2.0.0`, removed `sqlalchemy`, database drivers

#### 7. Update `src/mcp_server/__init__.py` ✓

- Version `2.0.0`

#### 8. Update `src/mcp_server/cli.py` ✓

- Manifest validation in `uavcrew status`
- Removed old database config, tools testing, seed data
- Added `CLIENT_API_TOKEN` and `MCP_MANIFEST_PATH` to setup wizard
- Added `uavcrew tenants add/list/remove` CLI commands (imports `tenant_db`)

#### 9. Delete old files ✓

- Deleted `http_server.py`, `tools/` directory, `database/` directory, `minio_client.py`

### Phase 2: Auth + Tenant DB (DONE)

#### 10. Create `src/mcp_server/tenant_db.py` ✓

Local SQLite store for `tenant_id → K4` mappings:
- `list_tenants() → list[dict]` — each dict has `tenant_id`, `name`, `created_at`
- `add_tenant(tenant_id, token, name)` — upsert
- `get_tenant_token(tenant_id) → str|None` — look up K4 by tenant_id
- `remove_tenant(tenant_id) → bool`

#### 11. Create `src/mcp_server/auth.py` ✓

JWT validation for T1 delegation tokens:
- `DelegationClaims` dataclass: `tenant_id`, `org_id`, `agent`, `scope`, `max_tier`, `session_id`, `jti`
- `load_public_key(path) → bytes|None` — load K3 from file
- `validate_delegation_token(token, public_key) → DelegationClaims|None` — RS256 verification, expiry, issuer, audience, fail closed

#### 12. Update `server.py` for auth (PENDING)

- Replace `BearerAuthMiddleware` with T1 JWT validation using K3
- Replace `_resolve_token(org_id)` with `tenant_db.get_tenant_token(tenant_id)`
- Remove `org_id` parameter from all tool signatures (tenant_id comes from T1)
- Add scope and tier checking to tool handlers

#### 13. Update `cli.py` tenant commands ✓

- `uavcrew tenants add/list/remove` — manages tenant_id → K4 mappings
- Imports from `tenant_db` module

### Phase 3: Gunicorn + Production Deployment

Align MCP Gateway deployment with AYNA Comply: gunicorn process manager, structured logging, proper systemd service.

**Current state:** `server.py` calls `uvicorn.run()` directly — single process, no worker management, no access logs, no graceful reloads.

**Target state:** Gunicorn with `uvicorn.workers.UvicornWorker` (ASGI equivalent of AYNA's sync workers), config file, log rotation, systemd `notify` type.

#### 14. Create `gunicorn_config.py`

Following the AYNA pattern (`/opt/ayna/ayna-comply/gunicorn_config.py`):

```python
import multiprocessing

# Server socket
bind = "127.0.0.1:8200"
backlog = 2048

# Worker processes — ASGI via uvicorn worker
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 30
graceful_timeout = 30
keepalive = 2

# Logging
accesslog = "/var/log/ayna/mcp-gateway/gunicorn-access.log"
errorlog = "/var/log/ayna/mcp-gateway/gunicorn-error.log"
loglevel = "info"
access_log_format = '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "mcp-gateway"

# Server mechanics
daemon = False
pidfile = None
```

Key differences from AYNA:
- `worker_class = "uvicorn.workers.UvicornWorker"` (ASGI) vs AYNA's `"sync"` (WSGI)
- Port `8200` vs AYNA's `8100`
- Log directory `/var/log/ayna/mcp-gateway/` (parallel to AYNA's `/var/log/ayna/ayna-comply/`)

#### 15. Add `gunicorn` to dependencies

- `pyproject.toml`: add `"gunicorn>=21.2.0"` to dependencies
- `requirements.txt`: add `gunicorn>=21.2.0`

#### 16. Update `server.py` entry point

Change `main()` from `uvicorn.run()` to gunicorn launch:

```python
def main():
    """Run the MCP Gateway via gunicorn."""
    from gunicorn.app.wsgiapp import WSGIApplication

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8200"))

    # Print startup banner before handing off to gunicorn
    # ...

    sys.argv = [
        "gunicorn",
        "--bind", f"{host}:{port}",
        "--config", str(Path(__file__).parent.parent.parent / "gunicorn_config.py"),
        "mcp_server.server:app",
    ]
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()
```

The ASGI `app` (FastAPI) is already the module-level variable. Gunicorn imports `mcp_server.server:app` directly.

Alternatively, keep `main()` as a simple dev-mode launcher (uvicorn direct) and let gunicorn be the production entry point via systemd. This matches AYNA's pattern where `manage.py runserver` is for dev and gunicorn is for production.

**Decision:** Keep both paths:
- `mcp-gateway` CLI command → gunicorn (production)
- `python -m mcp_server.server` → uvicorn direct (dev mode, for debugging)

#### 17. Update systemd unit generation in `cli.py`

Replace the current `generate_systemd_unit()` with a gunicorn-based service following AYNA's pattern:

```ini
[Unit]
Description=UAVCrew MCP Gateway
Documentation=https://docs.uavcrew.ai/mcp
After=network.target

[Service]
Type=notify
User={user}
Group={user}
WorkingDirectory={workdir}
EnvironmentFile={env_path}
Environment="PATH={venv}/bin"
ExecStart={venv}/bin/gunicorn \
    --bind {host}:{port} \
    --config {workdir}/gunicorn_config.py \
    mcp_server.server:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={workdir} /var/log/ayna/mcp-gateway

[Install]
WantedBy=multi-user.target
```

Changes from current unit:
- `Type=notify` instead of `simple` (gunicorn supports systemd notification)
- `ExecStart` calls gunicorn, not `python -m mcp_server.server`
- `ExecReload` for graceful worker restart via `HUP` signal
- `KillMode=mixed` + `TimeoutStopSec=30` for clean shutdown
- `Restart=on-failure` instead of `always` (matches AYNA)
- `ReadWritePaths` includes log directory
- `Environment="PATH=..."` for venv isolation

#### 18. Create log directory in setup

Add to `uavcrew setup` wizard or `generate-systemd`:
```bash
sudo mkdir -p /var/log/ayna/mcp-gateway
sudo chown {user}:{user} /var/log/ayna/mcp-gateway
```

#### 19. Update `uavcrew status` for gunicorn

Show gunicorn master + worker PIDs, worker count, and uptime. Check for gunicorn process name (`mcp-gateway`) instead of just port listening.

---

## Verification

### Phase 1 (DONE)

1. ✓ `pip install -e .` in venv
2. ✓ Create `manifest.json` from example
3. ✓ Start: `mcp-gateway`
4. ✓ Health: `curl http://localhost:8200/health`
5. ✓ MCP initialize via Streamable HTTP
6. ✓ Read manifest resource — verify 12 entities with reads + actions
7. ✓ List tools — verify 4 tools (get_entity, list_entities, search, action)
8. ✓ Test error cases (unknown entity, unknown action, read-only entity)

### Phase 2 (DONE — modules created, server integration PENDING)

9. ✓ `tenant_db.py` — 28 tests passing (add, get, list, remove, upsert, isolation)
10. ✓ `auth.py` — JWT validation (valid, expired, wrong key, wrong issuer/audience, missing claims)
11. ✓ CLI `tenants add/list/remove` — tested via `test_cli_tenants.py`

### Phase 3 (PENDING)

12. `pip install -e .` — gunicorn installed
13. `mcp-gateway` starts gunicorn with uvicorn workers
14. `curl http://localhost:8200/health` — responds through gunicorn
15. MCP tools work through gunicorn workers
16. `uavcrew generate-systemd` — produces gunicorn-based unit
17. `sudo systemctl start mcp-server` — gunicorn starts with correct workers
18. `kill -HUP <master>` — graceful worker reload
19. Access logs appear in `/var/log/ayna/mcp-gateway/gunicorn-access.log`
20. Error logs appear in `/var/log/ayna/mcp-gateway/gunicorn-error.log`

---
---

# Plan B: AYNA API Gaps

## Context

The MCP Gateway needs client API endpoints for all 12 entities. AYNA Comply (the reference client) has some but not all. This plan identifies what exists, what's missing, and what AYNA needs to build.

---

## Entity → AYNA API Status

| Entity | AYNA API Endpoint | Read | Write | Status |
|--------|------------------|------|-------|--------|
| `pilot` | `/api/v1/pilots/` | GET, GET/{id}, search, certification, training, currency, statistics | POST, PATCH, DELETE, POST certification, POST training | **COMPLETE** |
| `aircraft` | `/api/v1/drones/` | GET, GET/{id}, health, active-mission, missions | POST, PATCH, DELETE, POST maintenance, POST configuration | **COMPLETE** |
| `flight` | `/api/v1/flights/` | GET, GET/{id}, statistics | POST start, POST end, POST cancel, POST telemetry | **COMPLETE** |
| `mission` | `/api/v1/missions/` | GET, GET/{id}, flights, checklists | POST, PATCH, POST start, POST complete, POST checklists | **COMPLETE** |
| `maintenance` | Portal only (`/api/maintenance/`) | Portal UI only | Portal: start, complete, attachments | **NEEDS v1 API** |
| `checklist` | `/api/v1/checklists/` | GET templates, GET applicable | Completions via mission endpoints | **PARTIAL** |
| `company` | `/api/v1/organization/` | GET (single org) | None | **COMPLETE** (read-only) |
| `service` | None | None | None | **NEEDS MODEL + API** |
| `product` | None | None | None | **NEEDS MODEL + API** |
| `artifact` | `/api/v1/storage/` | GET files, GET file/{id}, presigned URLs | POST upload-url, POST register, PATCH, DELETE, POST move | **COMPLETE** |
| `crew` | `/api/v1/crew/` | GET, GET/{id}, roles, statistics | POST, PATCH, DELETE | **COMPLETE** |
| `parts` | Model exists (`DronePart`) | None | None | **NEEDS API** |

Also: `fleet` model exists but no API (not in our 12 entities, but worth noting).

---

## What AYNA Needs to Build

### Priority 1: `maintenance` API (model exists, needs API router)

AYNA has `MaintenanceRecord` model and `MaintenanceAttachment` model. Portal endpoints exist (`/api/maintenance/{pk}/start/`, `/api/maintenance/{pk}/complete/`). Needs a proper v1 API router.

**New file**: `apps/core/api/v1/maintenance.py`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/maintenance/` | List maintenance records (filter by drone, status, type, date range) |
| POST | `/api/v1/maintenance/` | Create maintenance record |
| GET | `/api/v1/maintenance/{id}` | Get maintenance record details |
| PATCH | `/api/v1/maintenance/{id}` | Update maintenance record |
| POST | `/api/v1/maintenance/{id}/start` | Start maintenance work |
| POST | `/api/v1/maintenance/{id}/complete` | Complete maintenance work |

**Schemas needed**: `MaintenanceIn`, `MaintenanceOut`, `MaintenanceUpdate`, `MaintenanceListFilters`

**Estimated effort**: Small — model and business logic exist, just needs API router + schemas. Portal endpoints can be referenced.

---

### Priority 2: `parts` API (model exists, needs API router)

AYNA has `DronePart` model with fields: `part_type`, `serial_number`, `part_code`, `status`, `health_status`, `total_usage_hours`, `installed_date`, `replaced_date`. Currently managed via Django admin only.

**New file**: `apps/core/api/v1/parts.py`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/parts/` | List parts (filter by drone, type, status) |
| POST | `/api/v1/parts/` | Register a new part |
| GET | `/api/v1/parts/{id}` | Get part details |
| PATCH | `/api/v1/parts/{id}` | Update part (status, usage hours) |
| DELETE | `/api/v1/parts/{id}` | Remove part from tracking |
| GET | `/api/v1/drones/{drone_id}/parts` | List parts for a specific drone |

**Schemas needed**: `PartIn`, `PartOut`, `PartUpdate`, `PartListFilters`

**Estimated effort**: Small — model exists, straightforward CRUD.

---

### Priority 3: `service` and `product` (need models + API)

These are business entities for STERLING agent. No models exist yet in AYNA.

**`Service` model** — services the operator offers or contracts:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `organization` | FK | Organization scoping |
| `name` | string | Service name (e.g., "Roof Inspection") |
| `description` | text | What the service includes |
| `service_type` | string | inspection, survey, mapping, photography, delivery, other |
| `price` | decimal | Base price |
| `currency` | string | USD, etc. |
| `duration_estimate` | integer | Estimated minutes |
| `is_active` | boolean | Available for booking |

**`Product` model** — products, equipment, payloads:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `organization` | FK | Organization scoping |
| `name` | string | Product name (e.g., "DJI Zenmuse H30T") |
| `description` | text | Product details |
| `product_type` | string | drone, payload, accessory, software, other |
| `manufacturer` | string | Manufacturer name |
| `model` | string | Model number |
| `serial_number` | string | Serial number (if tracked) |
| `price` | decimal | Price |
| `status` | string | active, discontinued, out_of_stock |

**New files**:
- `apps/core/models/service.py`
- `apps/core/models/product.py`
- `apps/core/api/v1/services.py`
- `apps/core/api/v1/products.py`
- Migration files

**API endpoints** (same pattern for both):

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/services/` | List services |
| POST | `/api/v1/services/` | Create service |
| GET | `/api/v1/services/{id}` | Get service |
| PATCH | `/api/v1/services/{id}` | Update service |
| DELETE | `/api/v1/services/{id}` | Delete service |

Same for `/api/v1/products/`.

**Estimated effort**: Medium — needs new models, migrations, schemas, and API routers.

---

### Priority 4: `checklist` API enhancements (optional)

Current checklist API is read-only (list templates, get applicable). Checklist completions are managed through mission endpoints. For the MCP, this works — agent reads checklists via `get_entity`/`list_entities` and updates via `action("mission", "update_checklist", ...)`.

No changes needed unless we want standalone checklist completion outside of missions.

---

### No changes needed

| Entity | Why |
|--------|-----|
| `pilot` | Full CRUD + certification + training API exists |
| `aircraft` | Full CRUD + health + maintenance + config API exists |
| `flight` | Full lifecycle API exists (start, end, cancel, telemetry) |
| `mission` | Full CRUD + lifecycle + checklists API exists |
| `company` | GET organization exists (read-only is correct) |
| `artifact` | Full storage API exists (upload, download, metadata, move) |
| `crew` | Full CRUD API exists |

---

### Search

AYNA already has unified search at `/api/v1/search/` with entity-type filtering. The MCP `search` tool can use this directly. Currently supports: pilot, mission, flight, drone, crew, fleet. Need to add: maintenance, parts, service, product to the search index.

---

## Summary

| Priority | Entity | Work | Effort |
|----------|--------|------|--------|
| P1 | `maintenance` | API router + schemas (model exists) | Small |
| P2 | `parts` | API router + schemas (model exists) | Small |
| P3 | `service` | Model + migration + API | Medium |
| P3 | `product` | Model + migration + API | Medium |
| P4 | `checklist` | Optional enhancements | Minimal |
| — | Search | Add new entities to search index | Small |

MCP Gateway can ship with the 8 entities that have complete APIs today. The remaining 4 (`maintenance`, `parts`, `service`, `product`) can be added to the manifest as AYNA builds the endpoints.
