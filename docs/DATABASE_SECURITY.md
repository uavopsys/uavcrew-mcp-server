# Database Security Guide

This guide explains how to securely configure your database for the MCP server, what data is exposed to UAVCrew, and how the schema mapping process works.

---

## How It Works

### What the MCP Server Exposes

The MCP server provides UAVCrew with **read-only access** to your database through these tools:

| Tool | Purpose | What It Returns |
|------|---------|-----------------|
| `list_tables` | Schema discovery | Table names and row counts |
| `describe_table` | Structure analysis | Column names, types, primary/foreign keys, 3 sample rows |
| `query_table` | Data retrieval | Query results (max 1000 rows per request) |

**Important:** The MCP server exposes your **raw database schema**. This is why proper security configuration is critical - you control what tables and columns are visible.

### What UAVCrew Does

When you connect an MCP server to UAVCrew, the following process occurs:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. CONNECTION VERIFICATION                                              │
│                                                                          │
│  UAVCrew calls your MCP server:                                         │
│  - GET /health          → Verify server is running, get version         │
│  - GET /mcp/tools       → List available tools                          │
│  - POST list_tables     → Confirm database connectivity                 │
│                                                                          │
│  Result: Connection status, server version, available tools displayed   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. SCHEMA DISCOVERY (Learn)                                             │
│                                                                          │
│  When you click "Learn", UAVCrew:                                       │
│  - Calls list_tables to get all table names                             │
│  - Calls describe_table for each table to get columns and sample data  │
│  - Sends schema to AI for analysis                                      │
│                                                                          │
│  AI analyzes your schema and produces a proposed mapping:               │
│  - Which table contains pilot data? → pilots, users, operators?         │
│  - Which column is the certificate expiry? → cert_exp, expiry_date?    │
│  - Which table has flight records? → flights, flight_logs, missions?   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. HUMAN APPROVAL (Required)                                            │
│                                                                          │
│  UAVCrew presents the proposed mapping for your review:                 │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Proposed Mapping                                    [Approve]  │   │
│  │                                                                  │   │
│  │  Pilots:                                                        │   │
│  │    Table: operators                                             │   │
│  │    pilot_id     ← operator_id                                   │   │
│  │    name         ← full_name                                     │   │
│  │    certificate  ← faa_cert_number                               │   │
│  │    expiry       ← cert_expiration_date                          │   │
│  │                                                                  │   │
│  │  Aircraft:                                                      │   │
│  │    Table: drones                                                │   │
│  │    aircraft_id  ← drone_id                                      │   │
│  │    registration ← faa_registration                              │   │
│  │    ...                                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  You can:                                                               │
│  - Approve the mapping as-is                                            │
│  - Edit incorrect mappings                                              │
│  - Exclude tables/columns that shouldn't be used                       │
│  - Re-run Learn if the mapping is significantly wrong                  │
│                                                                          │
│  Nothing is used until you explicitly approve.                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. COMPLIANCE ANALYSIS                                                  │
│                                                                          │
│  Once mapping is approved, UAVCrew can:                                 │
│  - Query your flight data using the approved mapping                    │
│  - Analyze compliance against FAA regulations                           │
│  - Generate compliance reports and scores                               │
│                                                                          │
│  All queries use query_table with the mapped table/column names.       │
│  UAVCrew only accesses data through your approved mapping.              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Database Security Configuration

### 1. Create a Read-Only Database User (Required)

Create a dedicated database user with minimal permissions. The MCP server only needs SELECT access.

#### PostgreSQL

```sql
-- Create the read-only user
CREATE USER mcp_readonly WITH PASSWORD 'use_a_strong_password_here';

-- Grant connection access
GRANT CONNECT ON DATABASE your_database TO mcp_readonly;
GRANT USAGE ON SCHEMA public TO mcp_readonly;

-- Grant SELECT only on compliance-relevant tables
GRANT SELECT ON TABLE
    pilots,
    aircraft,
    flights,
    missions,
    maintenance_records
TO mcp_readonly;

-- Explicitly deny access to sensitive tables
REVOKE ALL ON TABLE
    users,
    passwords,
    api_keys,
    billing,
    payments,
    credit_cards
FROM mcp_readonly;
```

#### MySQL

```sql
-- Create the read-only user
CREATE USER 'mcp_readonly'@'localhost' IDENTIFIED BY 'use_a_strong_password_here';

-- Grant SELECT only on specific tables
GRANT SELECT ON your_database.pilots TO 'mcp_readonly'@'localhost';
GRANT SELECT ON your_database.aircraft TO 'mcp_readonly'@'localhost';
GRANT SELECT ON your_database.flights TO 'mcp_readonly'@'localhost';
GRANT SELECT ON your_database.missions TO 'mcp_readonly'@'localhost';
GRANT SELECT ON your_database.maintenance_records TO 'mcp_readonly'@'localhost';

FLUSH PRIVILEGES;
```

#### SQL Server

```sql
-- Create the read-only user
CREATE LOGIN mcp_readonly WITH PASSWORD = 'use_a_strong_password_here';
CREATE USER mcp_readonly FOR LOGIN mcp_readonly;

-- Grant SELECT on specific tables
GRANT SELECT ON dbo.pilots TO mcp_readonly;
GRANT SELECT ON dbo.aircraft TO mcp_readonly;
GRANT SELECT ON dbo.flights TO mcp_readonly;
GRANT SELECT ON dbo.missions TO mcp_readonly;
GRANT SELECT ON dbo.maintenance_records TO mcp_readonly;

-- Deny access to sensitive tables
DENY SELECT ON dbo.users TO mcp_readonly;
DENY SELECT ON dbo.billing TO mcp_readonly;
```

### 2. Use Views to Control Column Exposure (Recommended)

Create database views that expose only the columns needed for compliance analysis. This provides an additional security layer and can anonymize sensitive data.

#### Example: Pilot View with PII Protection

```sql
-- Create a view that hides personal information
CREATE VIEW mcp_pilots AS
SELECT
    id AS pilot_id,

    -- Anonymize name (or use real name if you prefer)
    'Pilot-' || id AS name,

    -- Certification data (required for compliance)
    certificate_type,
    certificate_number,
    certificate_expiry,
    (certificate_expiry > CURRENT_DATE) AS certificate_valid,

    -- Waivers and qualifications
    waivers,
    bvlos_authorized,
    night_authorized,

    -- Flight experience
    total_flight_hours,
    flights_last_90_days

    -- EXCLUDED (not exposed):
    -- email, phone, address, ssn, emergency_contact,
    -- date_of_birth, drivers_license, bank_account

FROM pilots
WHERE active = true;  -- Only show active pilots

-- Grant access to the view, not the underlying table
REVOKE SELECT ON pilots FROM mcp_readonly;
GRANT SELECT ON mcp_pilots TO mcp_readonly;
```

#### Example: Flight View with Time Limitation

```sql
-- Only expose flights from the last 2 years
CREATE VIEW mcp_flights AS
SELECT
    id AS flight_id,
    pilot_id,
    aircraft_id,
    flight_datetime,
    duration_seconds,

    -- Location data
    takeoff_latitude,
    takeoff_longitude,
    max_altitude_ft,

    -- Telemetry summary
    telemetry_json,
    events_json,

    -- Compliance-relevant data
    airspace_class,
    laanc_authorization_id

    -- EXCLUDED:
    -- client_name, client_contact, billing_amount,
    -- internal_notes, crew_notes

FROM flights
WHERE flight_datetime > CURRENT_DATE - INTERVAL '2 years';

GRANT SELECT ON mcp_flights TO mcp_readonly;
```

#### Example: Aircraft View

```sql
CREATE VIEW mcp_aircraft AS
SELECT
    id AS aircraft_id,
    registration,           -- FAA N-number
    make,
    model,
    serial_number,

    -- Registration status
    registration_expiry,
    (registration_expiry > CURRENT_DATE) AS registration_valid,

    -- Maintenance data
    total_flight_hours,
    last_maintenance_date,
    hours_since_maintenance,
    maintenance_interval_hours,

    -- Technical info
    firmware_version,
    max_takeoff_weight_kg

    -- EXCLUDED:
    -- purchase_price, insurance_policy, storage_location,
    -- owner_contact, vendor_contact

FROM aircraft
WHERE status != 'decommissioned';

GRANT SELECT ON mcp_aircraft TO mcp_readonly;
```

### 3. Connection Security (Required)

#### Use SSL/TLS for Database Connections

Always encrypt the connection between the MCP server and your database.

```bash
# PostgreSQL with SSL
DATABASE_URL="postgresql://mcp_readonly:password@localhost:5432/yourdb?sslmode=require"

# MySQL with SSL
DATABASE_URL="mysql+pymysql://mcp_readonly:password@localhost:3306/yourdb?ssl=true"

# SQL Server with encryption
DATABASE_URL="mssql+pyodbc://mcp_readonly:password@localhost/yourdb?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=yes"
```

#### Network Isolation

The database should **never** be exposed to the internet. Only the MCP HTTP server should be accessible externally.

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR INFRASTRUCTURE                                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  PRIVATE NETWORK (not internet accessible)                │  │
│  │                                                           │  │
│  │  ┌──────────────┐         ┌──────────────┐              │  │
│  │  │   Database   │◀───────▶│  MCP Server  │              │  │
│  │  │  Port 5432   │  local  │  Port 8200   │              │  │
│  │  │  (blocked)   │  only   │  (internal)  │              │  │
│  │  └──────────────┘         └──────────────┘              │  │
│  │                                  │                        │  │
│  └──────────────────────────────────┼────────────────────────┘  │
│                                     │                           │
│  ┌──────────────────────────────────┼────────────────────────┐  │
│  │  DMZ / Reverse Proxy             │                        │  │
│  │                                  ▼                        │  │
│  │  ┌──────────────┐         ┌──────────────┐              │  │
│  │  │    Nginx     │────────▶│  Port 443    │◀─────────────┼──┼── UAVCrew
│  │  │   (HTTPS)    │         │  (public)    │   HTTPS      │  │
│  │  └──────────────┘         └──────────────┘              │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Firewall Configuration

```bash
# Block direct database access from outside
sudo ufw deny 5432/tcp   # PostgreSQL
sudo ufw deny 3306/tcp   # MySQL
sudo ufw deny 1433/tcp   # SQL Server

# Block direct MCP server access (use nginx proxy instead)
sudo ufw deny 8200/tcp

# Allow only HTTPS
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

---

## What Data Does UAVCrew Need?

For compliance analysis, UAVCrew needs access to these data categories:

### Required for Compliance Scoring

| Category | Purpose | Example Fields |
|----------|---------|----------------|
| **Pilot Certification** | Verify pilot is legally authorized | certificate_number, certificate_expiry, certificate_type |
| **Aircraft Registration** | Verify aircraft is registered | registration (N-number), registration_expiry |
| **Flight Telemetry** | Check altitude limits, geofence compliance | latitude, longitude, altitude_agl, timestamps |
| **Flight Metadata** | Associate flights with pilots/aircraft | flight_id, pilot_id, aircraft_id, flight_datetime |

### Recommended for Better Analysis

| Category | Purpose | Example Fields |
|----------|---------|----------------|
| **Maintenance Records** | Verify airworthiness | last_maintenance_date, hours_since_maintenance |
| **Mission Planning** | Compare planned vs actual | planned_altitude, geofence, airspace_class |
| **Waivers** | Check authorized operations | waivers[], bvlos_authorized, night_authorized |
| **Events/Logs** | Analyze flight incidents | arm/disarm events, mode changes, warnings |

### Not Needed (Can Be Excluded)

| Category | Examples |
|----------|----------|
| **Personal Contact Info** | Email, phone, home address, emergency contacts |
| **Financial Data** | Billing, payments, invoices, pricing |
| **Internal Notes** | Crew comments, client feedback, internal memos |
| **Authentication** | Passwords, API keys, tokens, sessions |
| **Business Data** | Client names, contracts, revenue |

---

## Security Checklist

Before connecting your MCP server to UAVCrew:

- [ ] Created dedicated read-only database user
- [ ] Granted SELECT only on compliance-relevant tables
- [ ] Revoked access to sensitive tables (users, billing, etc.)
- [ ] Created views to filter columns (if hiding PII)
- [ ] Enabled SSL/TLS for database connection
- [ ] Database port blocked from external access
- [ ] MCP server behind HTTPS reverse proxy (nginx/caddy)
- [ ] Firewall configured to allow only HTTPS (443)
- [ ] Strong API key configured in MCP_API_KEY
- [ ] Tested connection from UAVCrew dashboard

---

## Troubleshooting

### "Permission denied" errors

The mcp_readonly user doesn't have SELECT access to a table. Grant access:

```sql
GRANT SELECT ON table_name TO mcp_readonly;
```

### UAVCrew sees tables you want hidden

The user has access to tables it shouldn't. Revoke access:

```sql
REVOKE ALL ON sensitive_table FROM mcp_readonly;
```

### Schema discovery shows too many columns

Create views that expose only needed columns, then grant access to views instead of base tables.

### Connection refused

Check that:
1. Database is running
2. SSL is configured correctly
3. User credentials are correct
4. Firewall allows local connections

---

## Questions?

- **Documentation**: https://docs.uavcrew.ai/mcp
- **Support**: support@uavcrew.ai
- **Issues**: https://github.com/aelfakih/uavcrew-mcp-server/issues
