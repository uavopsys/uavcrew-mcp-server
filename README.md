# UAVCrew MCP Server

Client-deployable MCP (Model Context Protocol) server that exposes your drone operation data to UAVCrew's AI compliance analysis service.

## Overview

This MCP server runs in **your infrastructure** and provides secure, read-only access to your flight data. UAVCrew connects to discover your database schema, maps it to compliance entities, and performs analysis without you uploading sensitive files.

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR INFRASTRUCTURE                                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Your Data    │    │  MCP Server  │    │   HTTPS      │      │
│  │ (PostgreSQL, │───▶│  Port 8200   │◀───│  Nginx/Caddy │◀─────┼── UAVCrew AI
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

### 2. Run the Setup Wizard

```bash
uavcrew setup
```

The wizard will:
1. Configure your database connection
2. Set up the UAVCrew connection token
3. Generate reverse proxy configuration (Caddy/Nginx)
4. Create a systemd service for production

### 3. Start the Server

```bash
# Development
mcp-http-server

# Production (via systemd)
sudo systemctl start mcp-server
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uavcrew setup` | Interactive configuration wizard |
| `uavcrew status` | Check installation and service status |
| `uavcrew check` | Validate current configuration |
| `uavcrew keys list` | Show configured API keys |
| `uavcrew keys add <token>` | Add an API key from UAVCrew |
| `uavcrew keys remove <prefix>` | Remove an API key |
| `uavcrew map-data` | Configure database schema mapping |
| `uavcrew generate-systemd` | Generate systemd unit file |

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
| `MCP_SERVER_NAME` | No | `MCP Server` | Friendly name for UAVCrew dashboard |
| `MCP_PUBLIC_URL` | No | - | HTTPS URL where UAVCrew connects |
| `SEED_DEMO_DATA` | No | `false` | Seed demo data for testing |

### Example `.env` File

```bash
# Server Identity
MCP_SERVER_NAME=Production MCP
MCP_PUBLIC_URL=https://mcp.yourcompany.com

# Server Binding
MCP_HOST=127.0.0.1
MCP_PORT=8200

# Database
DATABASE_URL=postgresql://mcp_readonly:password@localhost:5432/compliance_db

# UAVCrew Connection
MCP_API_KEY=mcp_xxxxxxxxxxxxxxxxxxxx

# Security
SECRET_KEY=your-secret-key

# Development only
SEED_DEMO_DATA=false
```

---

## Database Setup

The MCP server connects to your existing database via SQLAlchemy. Install the driver for your database:

### PostgreSQL (Recommended)

```bash
pip install uavcrew-mcp-server[postgresql]
DATABASE_URL="postgresql://user:password@localhost:5432/your_db"
```

### MySQL / MariaDB

```bash
pip install uavcrew-mcp-server[mysql]
DATABASE_URL="mysql+pymysql://user:password@localhost:3306/your_db"
```

### SQLite (Testing Only)

```bash
# No driver needed
DATABASE_URL="sqlite:///./test.db"
```

### Microsoft SQL Server

```bash
pip install uavcrew-mcp-server[sqlserver]
DATABASE_URL="mssql+pyodbc://user:password@localhost/your_db?driver=ODBC+Driver+17+for+SQL+Server"
```

---

## Tools Exposed

The MCP server exposes these tools to UAVCrew:

### Schema Discovery Tools

These allow UAVCrew to discover your database structure:

| Tool | Description |
|------|-------------|
| `list_tables` | List all tables with row counts |
| `describe_table` | Get columns, types, primary keys, foreign keys, and sample data |
| `query_table` | Query raw data with column selection, WHERE, ORDER BY, and LIMIT |

### Mapped Entity Tools

Once UAVCrew maps your schema, these provide structured access:

| Tool | Description |
|------|-------------|
| `list_entities` | List available mapped entities |
| `describe_entity` | Describe entity fields |
| `query_entity` | Query entity data with filters |

### File Access Tools

For flight logs and documents:

| Tool | Description |
|------|-------------|
| `list_files` | List files in a directory |
| `read_file` | Read file content |
| `get_file_metadata` | Get file size, type, dates |

---

## Testing with Demo Data

For testing without your production data, enable demo data seeding:

```bash
# Set in .env
SEED_DEMO_DATA=true

# Or run directly
SEED_DEMO_DATA=true mcp-http-server
```

This creates sample tables with test scenarios:

### Demo Pilots

| ID | Name | Certificate | Status |
|----|------|-------------|--------|
| PLT-001 | John Smith | Part 107 | Valid (2026-05-15) |
| PLT-002 | Jane Doe | Part 107 | **EXPIRED** (2024-12-15) |
| PLT-003 | Bob Wilson | Part 107 + BVLOS | Valid (2027-03-01) |

### Demo Aircraft

| ID | Registration | Status |
|----|--------------|--------|
| AC-001 | N12345 | Valid, maintenance current |
| AC-002 | N67890 | **EXPIRED** registration |
| AC-003 | N11223 | Maintenance due soon |

### Demo Flights

| ID | Scenario | Expected Compliance |
|----|----------|---------------------|
| FLT-TC01 | Clean flight | COMPLIANT |
| FLT-TC02 | Altitude violation (485ft) | NEEDS_REVIEW |
| FLT-TC03 | Geofence breach | NON_COMPLIANT |
| FLT-TC04 | Expired pilot cert | NON_COMPLIANT |
| FLT-TC05 | Expired aircraft reg | NON_COMPLIANT |

### Testing the Server

```bash
# Health check
curl http://localhost:8200/health

# List available tools
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8200/mcp/tools

# List tables
curl -X POST http://localhost:8200/mcp/tools/call \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "list_tables", "arguments": {}}'

# Describe a table
curl -X POST http://localhost:8200/mcp/tools/call \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "describe_table", "arguments": {"table": "pilots"}}'

# Query data
curl -X POST http://localhost:8200/mcp/tools/call \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "query_table", "arguments": {"table": "pilots", "limit": 10}}'
```

---

## Security

**See [docs/DATABASE_SECURITY.md](docs/DATABASE_SECURITY.md) for comprehensive security configuration.**

Key requirements:

1. **Read-Only Database User** - Create a dedicated user with SELECT-only permissions
2. **Column Filtering** - Use views to expose only compliance-relevant fields
3. **PII Protection** - Anonymize or exclude personal information
4. **Network Isolation** - Database accessible only to MCP server, not internet
5. **HTTPS** - Always use a reverse proxy with SSL certificates

### HTTPS Setup

The MCP server listens on a local port. Use a reverse proxy for HTTPS:

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

See the full nginx configuration in `uavcrew setup` output.

---

## Deployment

### Systemd Service

The setup wizard can generate and install a systemd service:

```bash
uavcrew generate-systemd
```

Or manually:

```bash
sudo cat > /etc/systemd/system/mcp-server.service << 'EOF'
[Unit]
Description=UAVCrew MCP Server
After=network.target

[Service]
Type=simple
User=mcp
WorkingDirectory=/opt/uavcrew-mcp-server
EnvironmentFile=/opt/uavcrew-mcp-server/.env
ExecStart=/opt/uavcrew-mcp-server/venv/bin/python -m mcp_server.http_server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mcp-server
```

### Management Commands

```bash
# Start/stop/restart
sudo systemctl start mcp-server
sudo systemctl stop mcp-server
sudo systemctl restart mcp-server

# Check status
sudo systemctl status mcp-server

# View logs
sudo journalctl -u mcp-server -f
```

---

## Troubleshooting

### Server won't start

```bash
# Check configuration
uavcrew check

# View logs
sudo journalctl -u mcp-server -f
```

### UAVCrew can't connect

1. Check firewall allows HTTPS (port 443)
2. Verify SSL certificate is valid
3. Test API key: `curl -H "Authorization: Bearer KEY" https://your-mcp/health`

### Database connection fails

```bash
# Test connection
uavcrew check

# Verify DATABASE_URL in .env
cat .env | grep DATABASE_URL
```

### No tables returned

Verify the database user has SELECT permissions:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly;
```

---

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (returns version) |
| GET | `/mcp/tools` | List available tools |
| POST | `/mcp/tools/call` | Call a tool |

### Authentication

Include the API key in the Authorization header:

```
Authorization: Bearer mcp_xxxxxxxxxxxxxxxxxxxx
```

### Tool Call Format

```json
{
  "tool": "tool_name",
  "arguments": {
    "arg1": "value1",
    "arg2": "value2"
  }
}
```

### Response Format

```json
{
  "table": "pilots",
  "data": [...],
  "count": 3,
  "limit": 100
}
```

Or on error:

```json
{
  "success": false,
  "error": "Error message"
}
```

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/aelfakih/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License - See [LICENSE](LICENSE) file.
