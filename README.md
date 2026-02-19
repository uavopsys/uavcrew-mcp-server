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
│  │ API (Django, │<───│  Port 8200   │<───│  Nginx/Caddy │<─────┼── UAVCrew AI
│  │  Rails, etc) │    │  (gunicorn)  │    │  Port 443    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Your data stays on your network.** The gateway forwards only the API calls needed for compliance analysis.

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/aelfakih/uavcrew-mcp-server.git
cd uavcrew-mcp-server

python3.11 -m venv venv
source venv/bin/activate

pip install -e .
```

### 2. Run the Setup Wizard

```bash
uavcrew setup
```

The wizard will:
1. Configure server identity and public URL
2. Set the manifest path (entity definitions)
3. Set the client API base URL
4. Configure the UAVCrew API key
5. Generate reverse proxy configuration (Caddy/Nginx/Apache)
6. Create and install a systemd service

### 3. Register a Tenant

```bash
uavcrew tenants add --tenant-id <org-uuid> --token <api-key>
```

### 4. Start and Verify

```bash
uavcrew start
uavcrew status
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uavcrew setup` | Interactive configuration wizard |
| `uavcrew start` | Start the gateway service |
| `uavcrew stop` | Stop the gateway service |
| `uavcrew restart` | Restart the gateway service |
| `uavcrew status` | Show status, entities, auth mode, and service health |
| `uavcrew keys list` | List configured API keys |
| `uavcrew keys add <token>` | Add an API key from UAVCrew |
| `uavcrew keys remove <prefix>` | Remove an API key |
| `uavcrew tenants list` | List registered tenants |
| `uavcrew tenants add` | Register a tenant with their API token |
| `uavcrew tenants remove` | Remove a tenant |
| `uavcrew generate-systemd` | Generate and install systemd unit file |

---

## Configuration

### Environment Variables

Create a `.env` file (the setup wizard does this automatically):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_API_KEY` | Yes (prod) | - | API key for authenticating requests from UAVCrew |
| `CLIENT_API_BASE_URL` | No | from manifest | Base URL of your REST API |
| `MCP_HOST` | No | `127.0.0.1` | Server bind address |
| `MCP_PORT` | No | `8200` | Server port |
| `MCP_SERVER_NAME` | No | `MCP Gateway` | Friendly name for UAVCrew dashboard |
| `MCP_PUBLIC_URL` | No | - | HTTPS URL where UAVCrew connects |
| `MCP_JWT_PUBLIC_KEY_PATH` | No | - | Path to K3 public key for JWT auth |
| `CLIENT_API_TOKEN` | No | - | Client API token (K4) for static auth mode |
| `LOG_LEVEL` | No | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |

See [.env.example](.env.example) for a full template.

### Manifest

The gateway is driven by a `manifest.json` file that declares your entities, API paths, and available actions. See [manifest.json.example](manifest.json.example) for the full schema.

```json
{
  "api_base_url": "https://api.example.com/api/v1",
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

---

## Tools

The gateway exposes 4 tools and 1 resource to UAVCrew AI agents:

### Tools

| Tool | Description |
|------|-------------|
| `get_entity` | Get a single entity record by ID (or singleton like company) |
| `list_entities` | List entity records with filtering, sorting, and pagination |
| `search` | Search across one or all entity types |
| `action` | Execute a write action on an entity (create, update, start, etc.) |

### Resources

| Resource | Description |
|----------|-------------|
| `entities://manifest` | Entity definitions, paths, and available actions |

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check (version, entity count, auth mode) |
| `POST` | `/mcp` | Bearer | MCP Streamable HTTP endpoint |
| `GET` | `/tenants` | Bearer | List registered tenants |
| `POST` | `/tenants` | Bearer | Register a tenant |
| `DELETE` | `/tenants/{id}` | Bearer | Remove a tenant |

### Authentication

The gateway supports two authentication modes:

**JWT (recommended):** UAVCrew mints delegation tokens (T1) signed with RS256. The gateway validates using the K3 public key and resolves per-tenant API tokens (K4) from the tenant database.

**Static API key (legacy):** Single or multiple API keys via `MCP_API_KEY` / `MCP_API_KEYS` environment variables.

Include the token in the Authorization header:

```
Authorization: Bearer <token>
```

---

## Deployment

### Updating

```bash
cd /opt/ayna/uavcrew-mcp-server
git pull
source venv/bin/activate
pip install -e .
uavcrew restart
```

### Management

```bash
uavcrew start       # start the service
uavcrew stop        # stop the service
uavcrew restart     # restart the service
uavcrew status      # check health and configuration

# View logs
sudo journalctl -u mcp-server -f
```

---

## Testing

### Health Check

```bash
curl http://localhost:8200/health
```

### MCP Endpoint

The gateway uses MCP Streamable HTTP at `/mcp`. Connect using any MCP-compatible client:

```bash
# Using the MCP CLI
mcp connect http://localhost:8200/mcp --header "Authorization: Bearer YOUR_KEY"
```

---

## Security

1. **HTTPS** - Always use a reverse proxy with TLS termination
2. **API Keys** - Rotate keys regularly via the UAVCrew dashboard
3. **Per-Tenant Tokens** - Each tenant gets isolated API credentials (K4)
4. **Scope Enforcement** - T1 JWTs carry scoped permissions per entity and operation
5. **Network Isolation** - Bind to 127.0.0.1 behind a reverse proxy

### HTTPS Setup

The gateway listens on a local port. Use a reverse proxy for HTTPS:

**Caddy (recommended - automatic HTTPS):**

```
mcp.yourcompany.com {
    reverse_proxy localhost:8200
}
```

**Nginx:**

```bash
sudo certbot --nginx -d mcp.yourcompany.com
```

See the proxy configurations generated by `uavcrew setup`.

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

### Old version still running after update

```bash
uavcrew restart
```

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/aelfakih/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License - See [LICENSE](LICENSE) file.
