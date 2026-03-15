# UAVCrew MCP Gateway

Manifest-driven MCP Gateway that gives UAVCrew's AI agents secure access to your drone operation data through your existing REST API.

## Overview

The gateway runs on **your infrastructure** and translates MCP tool calls into authenticated HTTP requests against your REST API. UAVCrew's AI agents connect over HTTPS using the [Model Context Protocol](https://modelcontextprotocol.io/) to read, search, and act on your data — without direct database access.

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR INFRASTRUCTURE                                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Your REST    │    │ MCP Gateway  │    │   HTTPS      │      │
│  │ API (Django, │<───│  Port 8400   │<───│  Nginx/Caddy │<─────┼── UAVCrew AI
│  │  Rails, etc) │    │  (gunicorn)  │    │  Port 443    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Your data stays on your network.** The gateway forwards only the API calls needed for compliance analysis.

---

## Installation

### 1. Clone and Install

```bash
git clone https://github.com/uavopsys/uavcrew-mcp-server.git
cd uavcrew-mcp-server

python3 -m venv venv
source venv/bin/activate

pip install .
```

### 2. Run the Setup Wizard

```bash
uavcrew setup
```

The wizard will:
1. Configure server identity and public URL
2. Set the manifest path and client API base URL
3. Configure authentication mode
4. Save `.env` configuration
5. Generate reverse proxy configuration (Caddy/Nginx/Apache)
6. Create and install a systemd service

### 3. Start and Verify

```bash
uavcrew start
uavcrew status
curl http://localhost:8400/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "mcp-gateway",
  "version": "2.0.0",
  "entities": 12,
  "auth_mode": "jwt",
  "token_resolution": "dynamic"
}
```

### 4. Register on UAVCrew

1. Go to [UAVCrew Dashboard → MCP Servers](https://www.uavcrew.ai/dashboard/mcp/)
2. Add your server name, public URL, and connection type
3. For single-tenant: set `CLIENT_API_TOKEN` in `.env` and restart

UAVCrew connects using T1 delegation JWTs validated by the K3 public key
(shipped with this repo in `keys/k3_public.pem`). No manual token exchange needed.

---

## Management

```bash
uavcrew start       # Start the service
uavcrew stop        # Stop the service
uavcrew restart     # Restart after config changes
uavcrew status      # Check health, entities, auth mode

# View logs
sudo journalctl -u mcp-server -f
```

### Updating

```bash
cd /opt/ayna/uavcrew-mcp-server
git pull
source venv/bin/activate
pip install .
uavcrew restart
```

---

## Development

```bash
cd /opt/ayna/uavcrew-mcp-server
source venv/bin/activate
pip install -e ".[dev]"

make dev       # Start with gunicorn --reload
make test      # Run tests
make lint      # Run linter
```

Source changes are live with `--reload`. Health check: `curl http://localhost:8400/health`.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uavcrew setup` | Interactive configuration wizard |
| `uavcrew start` | Start the gateway service (systemd) |
| `uavcrew stop` | Stop the gateway service (systemd) |
| `uavcrew restart` | Restart the gateway service (systemd) |
| `uavcrew status` | Show status, entities, auth mode, and service health |
| `uavcrew keys list` | List configured API keys |
| `uavcrew keys add <token>` | Add an API key from UAVCrew |
| `uavcrew keys remove <prefix>` | Remove an API key |
| `uavcrew generate-systemd` | Generate and install systemd unit file |

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_JWT_PUBLIC_KEY_PATH` | Yes | `keys/k3_public.pem` | Path to K3 public key for validating T1 JWTs |
| `CLIENT_API_BASE_URL` | No | from manifest | Base URL of your REST API |
| `MCP_HOST` | No | `127.0.0.1` | Server bind address |
| `MCP_PORT` | No | `8400` | Server port |
| `MCP_SERVER_NAME` | No | `MCP Gateway` | Friendly name for UAVCrew dashboard |
| `MCP_PUBLIC_URL` | No | — | HTTPS URL where UAVCrew connects |
| `CLIENT_API_TOKEN` | No | — | Client API token (K4) for single-tenant static mode |
| `LOG_LEVEL` | No | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |

See [.env.example](.env.example) for a full template with auth mode documentation.

### Manifest

The gateway is driven by a `manifest.json` file that declares your entities, API paths, and available actions. See [manifest.json.example](manifest.json.example) for the full schema.

```json
{
  "api_base_url": "https://api.example.com/api/v1",
  "auth": {
    "mode": "dynamic",
    "resolver_path": "/internal/mcp/resolve-token"
  },
  "entities": {
    "pilot": {
      "path": "/pilots",
      "id_field": "id",
      "read": true,
      "search": true,
      "actions": {
        "create": { "method": "POST", "path": "/pilots" },
        "update": { "method": "PATCH", "path": "/pilots/{id}" }
      }
    }
  }
}
```

### Authentication Modes

The gateway supports two authentication modes, configured in `manifest.json`:

**Dynamic (recommended, multi-tenant):**

```json
{
  "auth": {
    "mode": "dynamic",
    "resolver_path": "/internal/mcp/resolve-token"
  }
}
```

UAVCrew sends T1 delegation JWTs signed with RS256. The gateway validates using the K3 public key and calls your resolver endpoint to get per-tenant API tokens (K4). Set `MCP_JWT_PUBLIC_KEY_PATH` in `.env`.

**Static (single-tenant):**

```json
{
  "auth": {
    "mode": "static",
    "token_env": "CLIENT_API_TOKEN"
  }
}
```

A single API token (K4) is used for all requests to your client API. Set `CLIENT_API_TOKEN` in `.env`. UAVCrew authenticates via T1 JWTs (validated with K3), same as dynamic mode.

---

## MCP Tools

The gateway exposes 4 tools and 1 resource to UAVCrew AI agents:

| Tool | Description |
|------|-------------|
| `get_entity` | Get a single entity record by ID (or singleton like company) |
| `list_entities` | List entity records with filtering, sorting, and pagination |
| `search` | Search across one or all entity types |
| `action` | Execute a write action on an entity (create, update, start, etc.) |

| Resource | Description |
|----------|-------------|
| `entities://manifest` | Entity definitions, paths, and available actions |

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check (version, entity count, auth mode) |
| `POST` | `/mcp` | Bearer | MCP Streamable HTTP endpoint |

### Connecting

```bash
# Health check
curl http://localhost:8400/health

# MCP endpoint (use any MCP-compatible client)
mcp connect http://localhost:8400/mcp --header "Authorization: Bearer YOUR_KEY"
```

---

## HTTPS Setup

The gateway listens on a local port. Always put a reverse proxy with TLS in front of it.

**Caddy (recommended — automatic HTTPS):**

```
mcp.yourcompany.com {
    reverse_proxy localhost:8400
}
```

**Nginx:**

```nginx
server {
    server_name mcp.yourcompany.com;
    location / {
        proxy_pass http://127.0.0.1:8400;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
# Then: sudo certbot --nginx -d mcp.yourcompany.com
```

The setup wizard (`uavcrew setup`) can generate these configs for you.

---

## Security

1. **HTTPS** — Always use a reverse proxy with TLS termination
2. **API Keys** — Rotate keys regularly via the UAVCrew dashboard
3. **Per-Tenant Tokens** — Each tenant gets isolated API credentials (K4)
4. **Scope Enforcement** — T1 JWTs carry scoped permissions per entity and operation
5. **Network Isolation** — Bind to 127.0.0.1 behind a reverse proxy

---

## Troubleshooting

### Server won't start

```bash
uavcrew status
sudo journalctl -u mcp-server -f
```

### UAVCrew can't connect

1. Check firewall allows HTTPS (port 443)
2. Verify SSL certificate is valid
3. Test health: `curl https://your-mcp-domain/health`
4. Check auth mode matches your UAVCrew configuration

### Config changes not taking effect

```bash
uavcrew restart
```

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/uavopsys/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License — See [LICENSE](LICENSE) file.
