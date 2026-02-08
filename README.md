# UAVCrew MCP Gateway

Client-deployable MCP Gateway that gives UAVCrew's AI agents secure access to your drone operation data — database, files, and object storage.

## Overview

This gateway runs on **your infrastructure** and provides controlled access to your data. UAVCrew's AI agents connect over HTTPS to discover your database schema, query compliance data, and access files — without you uploading anything.

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR INFRASTRUCTURE                                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Your Data    │    │ MCP Gateway  │    │   HTTPS      │      │
│  │ (PostgreSQL, │───>│  Port 8200   │<───│  Nginx/Caddy │<─────┼── UAVCrew AI
│  │  MySQL, etc) │    │  (local)     │    │  Port 443    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Your data stays on your network.** UAVCrew's AI queries only what it needs for compliance analysis.

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

Install your database driver:

```bash
# PostgreSQL (recommended)
pip install -e ".[postgresql]"

# MySQL / MariaDB
pip install -e ".[mysql]"

# SQL Server
pip install -e ".[sqlserver]"

# Oracle
pip install -e ".[oracle]"
```

### 2. Run the Setup Wizard

```bash
uavcrew setup
```

The wizard will:
1. Configure server identity and public URL
2. Set up your database connection
3. Configure the UAVCrew connection token
4. Generate reverse proxy configuration (Caddy/Nginx/Apache)
5. Create and install a systemd service
6. Restart the service

### 3. Verify

```bash
uavcrew status
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uavcrew status` | Check status, database, tools, and service |
| `uavcrew setup` | Interactive configuration wizard |
| `uavcrew keys list` | Show configured API keys |
| `uavcrew keys add <token>` | Add an API key from UAVCrew |
| `uavcrew keys remove <prefix>` | Remove an API key |
| `uavcrew generate-systemd` | Generate and install systemd unit file |

---

## Configuration

### Environment Variables

Create a `.env` file (the setup wizard does this automatically):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | Database connection string |
| `MCP_API_KEY` | Yes (prod) | - | Primary API key for authentication |
| `MCP_API_KEYS` | No | - | Additional API keys (comma-separated) |
| `MCP_HOST` | No | `127.0.0.1` | Server bind address |
| `MCP_PORT` | No | `8200` | Server port |
| `MCP_SERVER_NAME` | No | `MCP Gateway` | Friendly name for UAVCrew dashboard |
| `MCP_PUBLIC_URL` | No | - | HTTPS URL where UAVCrew connects |
| `SECRET_KEY` | No | auto-generated | Secret key for internal use |
| `SEED_DEMO_DATA` | No | `false` | Seed demo data for testing |
| `MINIO_ENDPOINT_URL` | No | - | MinIO/S3 endpoint for storage tools |
| `MINIO_ACCESS_KEY` | No | - | MinIO/S3 access key |
| `MINIO_SECRET_KEY` | No | - | MinIO/S3 secret key |
| `MINIO_BUCKET_PREFIX` | No | - | Bucket prefix for organization buckets |

See [.env.example](.env.example) for a full template.

---

## Tools

The gateway exposes 13 tools to UAVCrew AI agents:

### Database Tools

| Tool | Description |
|------|-------------|
| `list_tables` | List all tables with row counts |
| `describe_table` | Get columns, types, primary keys, foreign keys, and sample data |
| `query_table` | Query data with column selection, WHERE, ORDER BY, and LIMIT |

### File Access Tools

| Tool | Description |
|------|-------------|
| `list_files` | List files in a directory with optional pattern matching |
| `read_file` | Read file content |
| `get_file_metadata` | Get file size, type, modification dates |

### Storage Tools (MinIO/S3)

Requires `MINIO_*` environment variables to be configured.

| Tool | Description |
|------|-------------|
| `storage_list` | List files in organization storage bucket |
| `storage_get` | Get file content or presigned download URL |
| `storage_search` | Search files by name pattern |
| `storage_quota` | Check storage usage and limits |
| `storage_classify` | Tag files with classification metadata |
| `storage_notes` | Add notes/annotations to stored files |
| `storage_move` | Move or rename files within the bucket |

---

## API Endpoints

### REST API (used by UAVCrew)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check (returns service name and version) |
| GET | `/mcp/tools` | Bearer | List available tools |
| POST | `/mcp/tools/call` | Bearer | Call a tool |

### JSON-RPC 2.0 (MCP standard)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/jsonrpc` | Bearer | MCP-standard JSON-RPC 2.0 endpoint |

The JSON-RPC endpoint supports the standard MCP protocol methods:

- `initialize` - Returns server capabilities and protocol version
- `notifications/initialized` - Client acknowledgment (returns 202)
- `tools/list` - List available tools in MCP format
- `tools/call` - Call a tool, returns result in MCP content format
- `ping` - Keepalive

### Authentication

Include the API key in the Authorization header:

```
Authorization: Bearer mcp_xxxxxxxxxxxxxxxxxxxx
```

### REST Tool Call Format

```json
POST /mcp/tools/call

{
  "tool": "list_tables",
  "arguments": {}
}
```

### JSON-RPC Tool Call Format

```json
POST /jsonrpc

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_tables",
    "arguments": {}
  }
}
```

---

## Deployment

### Updating

```bash
cd /opt/ayna/uavcrew-mcp-server
git pull
source venv/bin/activate
pip install -e .
uavcrew generate-systemd    # regenerates unit file and restarts service
```

### Systemd Service

The setup wizard generates and installs a systemd service. You can also do it manually:

```bash
uavcrew generate-systemd
```

### Management Commands

```bash
# Start/stop/restart
sudo systemctl start mcp-server
sudo systemctl stop mcp-server
sudo systemctl restart mcp-server

# Check status
sudo systemctl status mcp-server
uavcrew status

# View logs
sudo journalctl -u mcp-server -f
```

---

## Testing

### Health Check

```bash
curl http://localhost:8200/health
```

### List Tools (REST)

```bash
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8200/mcp/tools
```

### Call a Tool (REST)

```bash
curl -X POST http://localhost:8200/mcp/tools/call \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "list_tables", "arguments": {}}'
```

### JSON-RPC Initialize

```bash
curl -X POST http://localhost:8200/jsonrpc \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### JSON-RPC Tool Call

```bash
curl -X POST http://localhost:8200/jsonrpc \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_tables","arguments":{}}}'
```

### Demo Data

For testing without production data:

```bash
SEED_DEMO_DATA=true mcp-gateway
```

---

## Security

**See [docs/DATABASE_SECURITY.md](docs/DATABASE_SECURITY.md) for comprehensive security configuration.**

Key requirements:

1. **Read-Only Database User** - Create a dedicated user with SELECT-only permissions
2. **Column Filtering** - Use views to expose only compliance-relevant fields
3. **PII Protection** - Anonymize or exclude personal information
4. **Network Isolation** - Database accessible only to MCP gateway, not internet
5. **HTTPS** - Always use a reverse proxy with SSL certificates
6. **API Keys** - Rotate keys regularly via the UAVCrew dashboard

### HTTPS Setup

The gateway listens on a local port. Use a reverse proxy for HTTPS:

**Caddy (Recommended - automatic HTTPS):**

```
mcp.yourcompany.com {
    reverse_proxy localhost:8200
}
```

**Nginx:**

```bash
sudo certbot --nginx -d mcp.yourcompany.com
```

See the full proxy configurations in `uavcrew setup` output.

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
3. Test API key: `curl -H "Authorization: Bearer KEY" https://your-mcp/health`

### Database connection fails

```bash
uavcrew status
```

### No tables returned

Verify the database user has SELECT permissions:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly;
```

### Old version still running after update

If `/health` returns an old version after `git pull && pip install`:

```bash
# Regenerate systemd unit (ensures venv python is used) and restart
uavcrew generate-systemd
```

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/aelfakih/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License - See [LICENSE](LICENSE) file.
