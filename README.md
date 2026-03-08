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

## Development

Prerequisites: Docker. The dev Dockerfile uses an editable pip install so volume-mounted source is live.

```bash
cd /opt/ayna/uavcrew-mcp-server
make up          # build dev image + start container (gunicorn --reload)
make logs        # tail logs
make restart     # restart gateway
make rebuild     # rebuild image + recreate (after dependency changes)
make down        # stop
```

Source code in `src/` is volume-mounted for live reload. Health check: `curl http://localhost:8400/health`.

---

## Deployment Options

The gateway can be deployed two ways:

| Method | Best for | How it works |
|--------|----------|-------------|
| **Docker** (recommended) | Most users | Pull the image, mount config, run |
| **Host install** | Advanced / custom setups | pip install into a venv, manage with systemd |

Both methods use the same configuration files (`.env` and `manifest.json`) and the same `uavcrew setup` wizard to generate them.

---

## Option A: Docker Deployment (Recommended)

### Prerequisites

- Docker and Docker Compose installed
- Python 3.10+ (only needed to run the setup wizard)

### 1. Install the Setup Tool

```bash
pip install uavcrew-mcp-server
```

Or clone the repo if you prefer:

```bash
git clone https://github.com/uavopsys/uavcrew-mcp-server.git
cd uavcrew-mcp-server
pip install .
```

### 2. Run the Setup Wizard

```bash
mkdir my-mcp-gateway && cd my-mcp-gateway
uavcrew setup --docker
```

The wizard walks you through:

1. **Server identity** — name, public URL, port
2. **Client API** — manifest path, your REST API base URL
3. **Authentication** — static (single tenant) or dynamic (multi-tenant) token resolution
4. **Save** — writes configuration to `config/` directory
5. **Docker Compose** — generates `docker-compose.yml`

After the wizard, your directory looks like this:

```
my-mcp-gateway/
├── docker-compose.yml
└── config/
    ├── .env              # Environment configuration
    ├── manifest.json     # Entity definitions and API paths
    └── keys/
        └── k3_public.pem # K3 public key (if auto-detected)
```

### 3. Edit Your Configuration

**`config/manifest.json`** — Define the entities your API exposes. See [manifest.json.example](manifest.json.example) for all options.

```json
{
  "api_base_url": "https://app.yourcompany.com/api/v1",
  "auth": {
    "mode": "static",
    "token_env": "CLIENT_API_TOKEN"
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

**`config/.env`** — Set your API credentials and any overrides. See [.env.example](.env.example) for all variables.

### 4. Start the Gateway

```bash
docker compose up -d
```

### 5. Verify

```bash
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

### 6. Register on UAVCrew

1. Go to [UAVCrew Dashboard → MCP Servers](https://www.uavcrew.ai/dashboard/mcp/)
2. Add your server name and public URL
3. Copy the connection token
4. Add it to `config/.env`:

   ```bash
   MCP_API_KEY=<token-from-dashboard>
   ```

5. Restart:

   ```bash
   docker compose restart
   ```

### Docker Management

```bash
docker compose up -d          # Start
docker compose down            # Stop
docker compose restart         # Restart after config changes
docker compose logs -f         # View logs (stdout)
docker compose pull            # Pull latest image
docker compose up -d           # Apply update
```

### Updating

```bash
docker compose pull
docker compose up -d
```

The image is published to `ghcr.io/uavopsys/uavcrew-mcp-server`. Tags follow semver:

| Tag | Description |
|-----|-------------|
| `latest` | Most recent release |
| `2.0.0` | Specific version |
| `2.0` | Latest patch in minor version |

### Docker Compose Reference

The generated `docker-compose.yml`:

```yaml
services:
  mcp-gateway:
    image: ghcr.io/uavopsys/uavcrew-mcp-server:latest
    container_name: mcp-gateway
    restart: unless-stopped
    ports:
      - "8400:8400"
    env_file:
      - ./config/.env
    volumes:
      - ./config/manifest.json:/app/config/manifest.json:ro
      - ./config/keys:/app/config/keys:ro
    environment:
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8400
```

You can override any `.env` value in the `environment` section. Environment variables take precedence over the env file.

### Manual Docker Setup (Without the Wizard)

If you prefer to skip the setup wizard, create the config directory yourself:

```bash
mkdir -p config/keys

# Copy and edit the example files
cp manifest.json.example config/manifest.json
cp .env.example config/.env

# Edit config/manifest.json with your entity definitions
# Edit config/.env with your credentials

# If using JWT auth, copy your K3 public key
cp /path/to/k3_public.pem config/keys/

# Start
docker compose up -d
```

---

## Option B: Host Install (venv + systemd)

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
curl http://localhost:8200/health
```

### Host Management

```bash
uavcrew start       # Start the service
uavcrew stop        # Stop the service
uavcrew restart     # Restart after config changes
uavcrew status      # Check health, entities, auth mode

# View logs
sudo journalctl -u mcp-server -f
```

### Updating (Host)

```bash
cd /opt/ayna/uavcrew-mcp-server
git pull
source venv/bin/activate
pip install .
uavcrew restart
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uavcrew setup` | Interactive configuration wizard |
| `uavcrew setup --docker` | Setup wizard for Docker deployment |
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
| `MCP_API_KEY` | Yes (prod) | — | API key for authenticating requests from UAVCrew |
| `CLIENT_API_BASE_URL` | No | from manifest | Base URL of your REST API |
| `MCP_HOST` | No | `127.0.0.1` | Server bind address (`0.0.0.0` in Docker) |
| `MCP_PORT` | No | `8400` | Server port |
| `MCP_SERVER_NAME` | No | `MCP Gateway` | Friendly name for UAVCrew dashboard |
| `MCP_PUBLIC_URL` | No | — | HTTPS URL where UAVCrew connects |
| `MCP_JWT_PUBLIC_KEY_PATH` | No | — | Path to K3 public key for JWT auth |
| `CLIENT_API_TOKEN` | No | — | Client API token (K4) for static auth mode |
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

UAVCrew sends T1 delegation JWTs signed with RS256. The gateway validates using the K3 public key and calls your resolver endpoint to get per-tenant API tokens (K4). Set `MCP_JWT_PUBLIC_KEY_PATH` in `.env` (Docker sets this automatically).

**Static (single-tenant):**

```json
{
  "auth": {
    "mode": "static",
    "token_env": "CLIENT_API_TOKEN"
  }
}
```

A single API key is used for all requests. Set `CLIENT_API_TOKEN` in `.env` with your client API key, and `MCP_API_KEY` with the token from the UAVCrew dashboard.

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

The host install wizard (`uavcrew setup`) can generate these configs for you. For Docker, configure the reverse proxy separately.

---

## Security

1. **HTTPS** — Always use a reverse proxy with TLS termination
2. **API Keys** — Rotate keys regularly via the UAVCrew dashboard
3. **Per-Tenant Tokens** — Each tenant gets isolated API credentials (K4)
4. **Scope Enforcement** — T1 JWTs carry scoped permissions per entity and operation
5. **Network Isolation** — Bind to 127.0.0.1 behind a reverse proxy (Docker handles this via port mapping)
6. **Read-Only Config** — Docker volumes are mounted as `:ro` (read-only)

---

## Troubleshooting

### Server won't start

**Docker:**
```bash
docker compose logs
```

**Host:**
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

**Docker:**
```bash
docker compose restart
```

**Host:**
```bash
uavcrew restart
```

### Container starts but /health returns error

Check that your config files are mounted correctly:

```bash
docker compose exec mcp-gateway ls -la /app/config/
docker compose exec mcp-gateway cat /app/config/manifest.json
```

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/uavopsys/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License — See [LICENSE](LICENSE) file.
