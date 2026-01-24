# UAVCrew Compliance MCP Server

Client-deployable MCP (Model Context Protocol) server that exposes your drone operation data to UAVCrew's AI compliance analysis service.

## Overview

This MCP server runs in **your infrastructure** and provides secure, real-time access to your flight data without uploading sensitive files to external services.

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR INFRASTRUCTURE                                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Flight Logs  │    │  Database    │    │  MCP Server  │      │
│  │ (.bin files) │───▶│ Your DB      │◀───│  Port 8200   │◀─────┼──── UAVCrew AI
│  └──────────────┘    └──────────────┘    └──────────────┘      │     (calls your
│                                                                 │      MCP server)
└─────────────────────────────────────────────────────────────────┘
```

**Your data never leaves your network.** UAVCrew's AI fetches only what it needs, processes it, and returns the compliance report.

---

## Prerequisites

Before setting up the MCP server, you need:

1. **A UAVCrew account** - Sign up at https://www.uavcrew.ai/
2. **An API key with `mcp:register` scope** - Create one at Dashboard → API Keys
   - Click "Create API Key"
   - Check the **MCP Register** permission
   - Save the key securely - it's only shown once

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/aelfakih/uavcrew-mcp-server.git
cd uavcrew-mcp-server
```

### 2. Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

```bash
pip install -e .
```

### 4. Run the Setup Wizard

The interactive setup wizard configures your database, registers with UAVCrew, and generates your `.env` file:

```bash
uavcrew setup --full
```

The wizard will:
1. **Configure your database** - Choose SQLite, PostgreSQL, MySQL, SQL Server, or Oracle
2. **Connect to UAVCrew** - Use your API key to auto-register (recommended) or paste a manual token
3. **Set server options** - Host, port, and demo data settings
4. **Validate configuration** - Test database connection and verify settings
5. **Generate systemd service** - Optional, for production deployment

### 5. Run the Server

There are two transport options:

**Option A: HTTP Server (for UAVCrew compliance service)**

```bash
# Development (with demo data)
PYTHONPATH=src python -m mcp_server.http_server

# Or use uvicorn directly
PYTHONPATH=src uvicorn mcp_server.http_server:app --host 0.0.0.0 --port 8200

# Production
MCP_API_KEY=your-secret-key DATABASE_URL=postgresql://... python -m mcp_server.http_server
```

**Option B: Stdio Server (for Claude Desktop integration)**

```bash
# Add to Claude Desktop config
python -m mcp_server.server
```

---

## Configuration

### Environment Variables

Create a `.env` file or set these environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./compliance_demo.db` | Database connection string |
| `MCP_API_KEY` | Yes (prod) | None | API key for authentication |
| `MCP_HOST` | No | `0.0.0.0` | Server bind address |
| `MCP_PORT` | No | `8200` | Server port |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `SEED_DEMO_DATA` | No | `true` | Seed demo data on startup |

### Example `.env` File

```bash
# Database
DATABASE_URL=postgresql://compliance_user:password@localhost:5432/compliance_db

# Security
MCP_API_KEY=your-secure-api-key-here

# Server
MCP_HOST=0.0.0.0
MCP_PORT=8200
LOG_LEVEL=INFO

# Development only
SEED_DEMO_DATA=false
```

---

## Database Setup

The MCP server supports multiple database backends via SQLAlchemy. Install the driver for your database and configure `DATABASE_URL`.

### SQLite (Development/Testing)

No driver needed - works out of the box.

```bash
DATABASE_URL="sqlite:///./compliance.db"
```

### PostgreSQL

```bash
pip install uavcrew-mcp-server[postgresql]
DATABASE_URL="postgresql://user:password@localhost:5432/compliance_db"
```

### MySQL / MariaDB

```bash
pip install uavcrew-mcp-server[mysql]
DATABASE_URL="mysql+pymysql://user:password@localhost:3306/compliance_db"
```

### Microsoft SQL Server

```bash
pip install uavcrew-mcp-server[sqlserver]
DATABASE_URL="mssql+pyodbc://user:password@localhost/compliance_db?driver=ODBC+Driver+17+for+SQL+Server"
```

### Oracle

```bash
pip install uavcrew-mcp-server[oracle]
DATABASE_URL="oracle+oracledb://user:password@localhost:1521/compliance_db"
```

### Database Schema

The MCP server expects these tables (created automatically on first run):

```sql
-- pilots: Pilot certifications
-- aircraft: Aircraft registration and status
-- flights: Flight records with telemetry
-- missions: Mission planning data
-- maintenance_records: Maintenance history
```

See `src/mcp_server/database/models.py` for full schema.

---

## Connecting Your Data

### Option A: Direct Database Connection

If your existing system uses PostgreSQL, point the MCP server at your database:

```bash
DATABASE_URL=postgresql://user:pass@your-db-host:5432/your_drone_db
```

You may need to create views or adjust the queries in `src/mcp_server/tools/` to match your schema.

### Option B: Data Sync

Sync data from your system to the MCP server's database:

```python
# Example: Sync from your system
from mcp_server.database import get_db
from mcp_server.database.models import Flight, Pilot, Aircraft

db = get_db()

# Add your flights
flight = Flight(
    id="FLT-2025-001",
    pilot_id="PLT-001",
    aircraft_id="AC-001",
    flight_datetime=datetime.now(),
    duration_seconds=1500,
    telemetry_json=json.dumps(your_telemetry_data),
    summary_json=json.dumps(your_summary),
)
db.add(flight)
db.commit()
```

### Option C: Custom Tool Implementation

Modify the tools in `src/mcp_server/tools/` to fetch from your existing APIs:

```python
# src/mcp_server/tools/flight_log.py
def get_flight_log(db, flight_id: str) -> dict:
    # Instead of querying local DB, call your API
    response = requests.get(f"https://your-api.com/flights/{flight_id}")
    return response.json()
```

---

## Tools Exposed

The MCP server exposes these tools to UAVCrew's AI:

| Tool | Description | Required Fields |
|------|-------------|-----------------|
| `get_flight_log` | Flight telemetry and events | `flight_id` |
| `get_pilot` | Pilot certification status | `pilot_id` |
| `get_aircraft` | Aircraft registration status | `aircraft_id` |
| `get_mission` | Mission planning data | `flight_id` |
| `get_maintenance_history` | Maintenance records | `aircraft_id` |

### Data Formats

See [docs/DATA_FORMATS.md](docs/DATA_FORMATS.md) for detailed schema documentation.

---

## Security

### Network Security

1. **Firewall**: Only allow connections from UAVCrew IP addresses
   ```bash
   # Example: UFW
   sudo ufw allow from 34.xxx.xxx.xxx to any port 8200
   ```

2. **HTTPS**: Use a reverse proxy (nginx/caddy) with TLS
   ```nginx
   server {
       listen 443 ssl;
       server_name mcp.yourcompany.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       location / {
           proxy_pass http://127.0.0.1:8200;
       }
   }
   ```

3. **API Key**: Set a strong `MCP_API_KEY` and share it with UAVCrew

### Data Security

- **Least Privilege**: Only expose fields needed for compliance analysis
- **No PII Export**: Pilot names can be anonymized if needed
- **Audit Logging**: All requests are logged with timestamps

---

## Testing

### 1. Start the HTTP Server with Demo Data

```bash
# This seeds test flights, pilots, and aircraft
SEED_DEMO_DATA=true PYTHONPATH=src python -m mcp_server.http_server
```

### 2. Test Database and Tools

```bash
# Run the comprehensive test script
PYTHONPATH=src python scripts/test_connection.py --seed
```

### 3. Test with curl

```bash
# Health check
curl http://localhost:8200/health

# List available tools
curl http://localhost:8200/tools

# Call get_flight_log via JSON-RPC
curl -X POST http://localhost:8200/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_flight_log",
      "arguments": {"flight_id": "FLT-TC01"}
    },
    "id": 1
  }'

# Call get_pilot
curl -X POST http://localhost:8200/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "get_pilot",
      "arguments": {"pilot_id": "PLT-001"}
    },
    "id": 2
  }'
```

### 4. Test with UAVCrew Service

Once your MCP server is running and accessible:

1. Log into UAVCrew dashboard at https://www.uavcrew.ai/accounts/login/
2. Go to Dashboard → MCP Servers (`/dashboard/mcp/`)
3. Click on your registered server to view details
4. Click "Test Connection" to verify UAVCrew can reach your server
5. If successful, submit a flight for compliance analysis

---

## Demo Data

The server includes demo data for testing (set `SEED_DEMO_DATA=true`):

### Demo Flights

| Flight ID | Scenario | Expected Result |
|-----------|----------|-----------------|
| `FLT-TC01` | Clean flight | COMPLIANT (95-100) |
| `FLT-TC02` | Altitude violation | NEEDS_REVIEW (60-75) |
| `FLT-TC03` | Geofence breach | NON_COMPLIANT (40-55) |
| `FLT-TC04` | Expired pilot cert | NON_COMPLIANT (30-50) |
| `FLT-TC05` | Expired aircraft reg | NON_COMPLIANT (30-50) |

### Demo Pilots

| Pilot ID | Name | Certificate | Status |
|----------|------|-------------|--------|
| `PLT-001` | John Smith | Part 107 | Valid (expires 2026-05-15) |
| `PLT-002` | Jane Doe | Part 107 | **EXPIRED** (2024-12-15) |
| `PLT-003` | Bob Wilson | Part 107 + BVLOS | Valid (expires 2027-03-01) |

### Demo Aircraft

| Aircraft ID | Registration | Status |
|-------------|--------------|--------|
| `AC-001` | N12345 | Valid, maintenance current |
| `AC-002` | N67890 | **EXPIRED** registration |
| `AC-003` | N11223 | Valid, maintenance due soon |

---

## Deployment

### Systemd Service (Linux)

```bash
# Create service file
sudo cat > /etc/systemd/system/mcp-server.service << 'EOF'
[Unit]
Description=UAVCrew Compliance MCP Server
After=network.target postgresql.service

[Service]
Type=simple
User=mcp
Group=mcp
WorkingDirectory=/opt/uavcrew-mcp-server
Environment="DATABASE_URL=postgresql://..."
Environment="MCP_API_KEY=your-key"
Environment="MCP_PORT=8200"
ExecStart=/opt/uavcrew-mcp-server/venv/bin/python -m mcp_server.http_server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable mcp-server
sudo systemctl start mcp-server
```

---

## Troubleshooting

### Server won't start

```bash
# Check logs
journalctl -u mcp-server -f

# Test database connection
python -c "from mcp_server.database import get_db; print(get_db())"
```

### UAVCrew can't connect

1. Check firewall allows UAVCrew IPs
2. Verify HTTPS certificate is valid
3. Test API key: `curl -H "Authorization: Bearer KEY" https://your-mcp/health`

### No data returned

1. Verify data exists: `python -c "from mcp_server.database import get_db; from mcp_server.database.models import Flight; print(get_db().query(Flight).count())"`
2. Check flight ID matches exactly
3. Review logs for errors

---

## Support

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Issues**: https://github.com/aelfakih/uavcrew-mcp-server/issues
- **Email**: support@uavcrew.ai

---

## License

MIT License - See [LICENSE](LICENSE) file.
