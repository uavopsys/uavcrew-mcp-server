"""
UAVCrew MCP Server CLI

Interactive setup wizard and configuration tools.

Usage:
    uavcrew status             # Check installation and service status
    uavcrew setup              # Interactive configuration wizard
    uavcrew map-data           # Configure data source mappings
    uavcrew check              # Validate current configuration
    uavcrew generate-systemd   # Generate systemd unit file
"""

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(
    name="uavcrew",
    help="UAVCrew MCP Server configuration and management tools.",
    no_args_is_help=True,
)
console = Console()

# Database configuration templates
DB_CONFIGS = {
    "sqlite": {
        "driver": None,  # Built-in
        "pip_package": None,
        "url_template": "sqlite:///{path}",
        "default_path": "./compliance.db",
    },
    "postgresql": {
        "driver": "psycopg2",
        "pip_package": "psycopg2-binary",
        "url_template": "postgresql://{user}:{password}@{host}:{port}/{database}",
        "default_port": "5432",
    },
    "mysql": {
        "driver": "pymysql",
        "pip_package": "pymysql",
        "url_template": "mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
        "default_port": "3306",
    },
    "sqlserver": {
        "driver": "pyodbc",
        "pip_package": "pyodbc",
        "url_template": "mssql+pyodbc://{user}:{password}@{host}/{database}?driver=ODBC+Driver+17+for+SQL+Server",
        "default_port": "1433",
    },
    "oracle": {
        "driver": "oracledb",
        "pip_package": "oracledb",
        "url_template": "oracle+oracledb://{user}:{password}@{host}:{port}/{database}",
        "default_port": "1521",
    },
}


def check_driver_installed(db_type: str) -> bool:
    """Check if the database driver is installed."""
    config = DB_CONFIGS[db_type]
    driver = config.get("driver")
    if driver is None:
        return True  # SQLite - no driver needed
    try:
        __import__(driver)
        return True
    except ImportError:
        return False


def install_driver(db_type: str) -> bool:
    """Install the database driver via pip."""
    config = DB_CONFIGS[db_type]
    package = config.get("pip_package")
    if package is None:
        return True  # No package needed

    console.print(f"Installing {package}...", style="yellow")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        console.print(f"Installed {package}", style="green")
        return True
    except subprocess.CalledProcessError:
        console.print(f"Failed to install {package}", style="red")
        return False


def build_database_url(db_type: str, existing: dict = None) -> str:
    """Interactively build a database URL."""
    config = DB_CONFIGS[db_type]
    existing = existing or {}

    if db_type == "sqlite":
        default_path = existing.get("db_path", config["default_path"])
        path = Prompt.ask("Database file path", default=default_path)
        return config["url_template"].format(path=path)

    # For all other databases, prompt for connection details
    host = Prompt.ask("Host", default=existing.get("db_host", "localhost"))
    port = Prompt.ask("Port", default=existing.get("db_port", config.get("default_port", "")))
    database = Prompt.ask("Database name", default=existing.get("db_name", ""))
    user = Prompt.ask("Username", default=existing.get("db_user", ""))
    password = Prompt.ask("Password", password=True)

    return config["url_template"].format(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )


def test_database_connection(url: str) -> tuple[bool, str]:
    """Test database connection and return (success, message)."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def generate_secret_key() -> str:
    """Generate a cryptographically secure secret key."""
    return secrets.token_urlsafe(32)


def load_env_file(path: Path) -> dict:
    """Load environment variables from .env file."""
    env = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def write_env_file(path: Path, config: dict) -> None:
    """Write configuration to .env file."""
    lines = [
        "# UAVCrew MCP Server Configuration",
        "# Generated by: uavcrew setup",
        "",
        "# Server Identity",
        f"MCP_SERVER_NAME={config.get('MCP_SERVER_NAME', 'MCP Server')}",
        f"MCP_PUBLIC_URL={config.get('MCP_PUBLIC_URL', '')}",
        "",
        "# Server Binding",
        f"MCP_HOST={config.get('MCP_HOST', '0.0.0.0')}",
        f"MCP_PORT={config.get('MCP_PORT', '8200')}",
        "",
        "# Database",
        f"DATABASE_URL={config.get('DATABASE_URL', '')}",
        "",
        "# UAVCrew Connection",
        f"MCP_API_KEY={config.get('MCP_API_KEY', '')}",
        "",
        "# Security",
        f"SECRET_KEY={config.get('SECRET_KEY', '')}",
        "",
        "# Options",
        f"SEED_DEMO_DATA={config.get('SEED_DEMO_DATA', 'false')}",
        "",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines))


def detect_paths() -> dict:
    """Detect virtualenv, working directory, and user."""
    return {
        "workdir": Path.cwd().resolve(),
        "venv": Path(sys.prefix).resolve() if sys.prefix != sys.base_prefix else None,
        "python": Path(sys.executable).resolve(),
        "user": os.environ.get("USER", "root"),
    }


def generate_systemd_unit(paths: dict, env_path: Path) -> str:
    """Generate systemd unit file content."""
    exec_start = f"{paths['python']} -m mcp_server.http_server"

    return f"""[Unit]
Description=UAVCrew MCP Server
Documentation=https://docs.uavcrew.ai/mcp
After=network.target

[Service]
Type=simple
User={paths['user']}
Group={paths['user']}
WorkingDirectory={paths['workdir']}
EnvironmentFile={env_path.resolve()}
ExecStart={exec_start}
Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={paths['workdir']}

[Install]
WantedBy=multi-user.target
"""


def generate_caddy_config(domain: str) -> str:
    """Generate Caddyfile configuration."""
    return f"""{domain} {{
    reverse_proxy localhost:8200
}}
"""


def generate_nginx_config(domain: str) -> str:
    """Generate nginx configuration."""
    return f"""server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {domain};

    # SSL certificates - update paths after running certbot
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;

    location / {{
        proxy_pass http://127.0.0.1:8200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


def generate_apache_config(domain: str) -> str:
    """Generate Apache configuration."""
    return f"""<VirtualHost *:80>
    ServerName {domain}
    Redirect permanent / https://{domain}/
</VirtualHost>

<VirtualHost *:443>
    ServerName {domain}

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/{domain}/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/{domain}/privkey.pem

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8200/
    ProxyPassReverse / http://127.0.0.1:8200/

    <Location />
        Require all granted
    </Location>
</VirtualHost>
"""


# =============================================================================
# Data Mapping Schema
# =============================================================================

# Define the compliance data schema that MCP tools expect
DATA_SCHEMA = {
    "pilots": {
        "description": "Pilot certifications and credentials",
        "fields": {
            "id": {"type": "string", "required": True, "description": "Unique pilot identifier"},
            "name": {"type": "string", "required": True, "description": "Pilot's full name"},
            "certificate_type": {"type": "string", "required": True, "description": "Certificate type (Part 107, Part 61, etc.)"},
            "certificate_number": {"type": "string", "required": True, "description": "FAA certificate number"},
            "certificate_expiry": {"type": "date", "required": True, "description": "Certificate expiration date"},
            "certificate_valid": {"type": "boolean", "required": False, "description": "Whether certificate is currently valid"},
            "flight_hours_total": {"type": "float", "required": False, "description": "Total flight hours"},
            "flight_hours_90_days": {"type": "float", "required": False, "description": "Flight hours in last 90 days"},
        },
    },
    "aircraft": {
        "description": "Aircraft/drone registration and status",
        "fields": {
            "id": {"type": "string", "required": True, "description": "Unique aircraft identifier"},
            "registration": {"type": "string", "required": True, "description": "FAA registration number (N-number)"},
            "make_model": {"type": "string", "required": True, "description": "Aircraft make and model"},
            "serial_number": {"type": "string", "required": True, "description": "Manufacturer serial number"},
            "registration_expiry": {"type": "date", "required": True, "description": "Registration expiration date"},
            "registration_valid": {"type": "boolean", "required": False, "description": "Whether registration is current"},
            "total_flight_hours": {"type": "float", "required": False, "description": "Total airframe hours"},
            "last_maintenance_date": {"type": "date", "required": False, "description": "Date of last maintenance"},
        },
    },
    "flights": {
        "description": "Flight records with telemetry data",
        "fields": {
            "id": {"type": "string", "required": True, "description": "Unique flight identifier"},
            "pilot_id": {"type": "string", "required": True, "description": "Reference to pilot"},
            "aircraft_id": {"type": "string", "required": True, "description": "Reference to aircraft"},
            "flight_datetime": {"type": "datetime", "required": True, "description": "Flight start date/time"},
            "duration_seconds": {"type": "integer", "required": True, "description": "Flight duration in seconds"},
            "max_altitude_ft": {"type": "float", "required": False, "description": "Maximum altitude AGL in feet"},
            "max_speed_mph": {"type": "float", "required": False, "description": "Maximum ground speed in mph"},
            "takeoff_lat": {"type": "float", "required": False, "description": "Takeoff latitude"},
            "takeoff_lon": {"type": "float", "required": False, "description": "Takeoff longitude"},
        },
    },
    "missions": {
        "description": "Mission planning and authorization data",
        "fields": {
            "id": {"type": "string", "required": True, "description": "Unique mission identifier"},
            "flight_id": {"type": "string", "required": False, "description": "Reference to associated flight"},
            "purpose": {"type": "string", "required": True, "description": "Mission purpose/type"},
            "location_name": {"type": "string", "required": True, "description": "Location description"},
            "location_lat": {"type": "float", "required": True, "description": "Mission center latitude"},
            "location_lon": {"type": "float", "required": True, "description": "Mission center longitude"},
            "airspace_class": {"type": "string", "required": False, "description": "Airspace classification (A-G)"},
            "laanc_authorization_id": {"type": "string", "required": False, "description": "LAANC authorization ID if required"},
            "planned_altitude_ft": {"type": "float", "required": False, "description": "Planned max altitude in feet"},
        },
    },
    "maintenance": {
        "description": "Aircraft maintenance records",
        "fields": {
            "id": {"type": "string", "required": True, "description": "Unique maintenance record ID"},
            "aircraft_id": {"type": "string", "required": True, "description": "Reference to aircraft"},
            "date": {"type": "date", "required": True, "description": "Maintenance date"},
            "type": {"type": "string", "required": True, "description": "Maintenance type (scheduled, unscheduled, repair)"},
            "description": {"type": "string", "required": True, "description": "Work performed"},
            "technician": {"type": "string", "required": False, "description": "Technician name"},
            "hours_at_service": {"type": "float", "required": False, "description": "Airframe hours at service"},
        },
    },
}


def load_data_mapping(path: Path) -> dict:
    """Load existing data mapping from YAML file."""
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_data_mapping(path: Path, mapping: dict) -> None:
    """Save data mapping to YAML file."""
    with open(path, "w") as f:
        yaml.dump(mapping, f, default_flow_style=False, sort_keys=False)


def get_database_tables(db_url: str) -> list[str]:
    """Get list of tables from database."""
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(db_url)
        inspector = inspect(engine)
        return inspector.get_table_names()
    except Exception as e:
        console.print(f"  [yellow]Could not list tables: {e}[/yellow]")
        return []


def get_table_columns(db_url: str, table_name: str) -> list[str]:
    """Get list of columns from a table."""
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(db_url)
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        return [col["name"] for col in columns]
    except Exception as e:
        console.print(f"  [yellow]Could not list columns: {e}[/yellow]")
        return []


@app.command("map-data")
def map_data():
    """Configure data source mappings for your existing database schema."""
    console.print(
        Panel.fit(
            "[bold blue]UAVCrew MCP Server - Data Mapping[/bold blue]\n\n"
            "This wizard maps your existing database schema to the compliance data format.\n"
            "UAVCrew needs to know where your pilots, aircraft, flights, and other data lives.",
            border_style="blue",
        )
    )

    mapping_path = Path.cwd() / "data_mapping.yaml"
    env_path = Path.cwd() / ".env"

    # Load existing mapping if available
    existing = load_data_mapping(mapping_path)
    if existing:
        console.print("\n[yellow]Found existing data_mapping.yaml. Values will be used as defaults.[/yellow]")

    # Load database URL from .env
    db_url = None
    if env_path.exists():
        env_vars = load_env_file(env_path)
        db_url = env_vars.get("DATABASE_URL")

    if not db_url:
        console.print("\n[red]No DATABASE_URL found in .env[/red]")
        console.print("Run [cyan]uavcrew setup[/cyan] first to configure your database connection.")
        raise typer.Exit(1)

    # Get available tables
    console.print("\n[bold]Connecting to database...[/bold]")
    tables = get_database_tables(db_url)
    if tables:
        console.print(f"  [green]✓[/green] Found {len(tables)} tables: {', '.join(tables[:10])}{'...' if len(tables) > 10 else ''}")
    else:
        console.print("  [yellow]![/yellow] Could not list tables. You'll need to enter table names manually.")

    mapping = {"version": "1.0", "source_type": "database", "entities": {}}

    # =========================================================================
    # Walk through each entity
    # =========================================================================
    for entity_name, entity_schema in DATA_SCHEMA.items():
        console.print("\n" + "=" * 60)
        console.print(f"[bold cyan]{entity_name.upper()}[/bold cyan] - {entity_schema['description']}")
        console.print("=" * 60)

        # Check if entity should be mapped
        existing_entity = existing.get("entities", {}).get(entity_name, {})
        default_enabled = bool(existing_entity.get("source_table"))

        if not Confirm.ask(f"\n  Do you have {entity_name} data to map?", default=default_enabled):
            console.print(f"  [dim]Skipping {entity_name}[/dim]")
            continue

        # Get source table
        console.print(f"\n  [bold]Source Table[/bold]")
        console.print(f"  Which table contains your {entity_name} data?")
        if tables:
            console.print(f"  Available tables: {', '.join(tables)}")

        default_table = existing_entity.get("source_table", entity_name)
        source_table = Prompt.ask(
            f"  Table name",
            default=default_table,
        )

        # Get columns from source table
        columns = get_table_columns(db_url, source_table)
        if columns:
            console.print(f"  [green]✓[/green] Found columns: {', '.join(columns[:15])}{'...' if len(columns) > 15 else ''}")

        # Map each field
        console.print(f"\n  [bold]Column Mappings[/bold]")
        console.print(f"  Map your columns to the compliance data format.")
        console.print(f"  Press Enter to skip optional fields, or type '-' to explicitly skip.\n")

        field_mappings = {}
        existing_mappings = existing_entity.get("columns", {})

        for field_name, field_info in entity_schema["fields"].items():
            required = field_info["required"]
            field_type = field_info["type"]
            description = field_info["description"]

            # Determine default value
            default = existing_mappings.get(field_name, "")
            if not default and field_name in columns:
                default = field_name  # Auto-match if column name matches

            # Format prompt
            req_marker = "[red]*[/red]" if required else "[dim](optional)[/dim]"
            type_hint = f"[dim]{field_type}[/dim]"

            console.print(f"  {req_marker} [cyan]{field_name}[/cyan] {type_hint}")
            console.print(f"      {description}")

            column = Prompt.ask(
                f"      Your column",
                default=default,
            )

            if column and column != "-":
                field_mappings[field_name] = column
            elif required and not column:
                console.print(f"      [yellow]Warning: {field_name} is required for compliance checks[/yellow]")

        # Optional: Add custom WHERE clause
        console.print(f"\n  [bold]Filter (Optional)[/bold]")
        console.print(f"  Add a WHERE clause to filter records (e.g., 'status = active')")
        default_filter = existing_entity.get("filter", "")
        filter_clause = Prompt.ask(
            f"  WHERE clause",
            default=default_filter,
        )

        # Save entity mapping
        mapping["entities"][entity_name] = {
            "source_table": source_table,
            "columns": field_mappings,
        }
        if filter_clause:
            mapping["entities"][entity_name]["filter"] = filter_clause

        console.print(f"\n  [green]✓[/green] Mapped {entity_name}: {source_table} → {len(field_mappings)} fields")

    # =========================================================================
    # Save mapping
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]SAVE CONFIGURATION[/bold cyan]")
    console.print("=" * 60)

    # Show summary
    console.print("\n[bold]Mapping Summary:[/bold]")
    summary_table = Table()
    summary_table.add_column("Entity", style="cyan")
    summary_table.add_column("Source Table", style="white")
    summary_table.add_column("Fields Mapped", style="green")

    for entity_name, entity_config in mapping["entities"].items():
        summary_table.add_row(
            entity_name,
            entity_config["source_table"],
            str(len(entity_config["columns"])),
        )

    console.print(summary_table)

    # Save
    save_data_mapping(mapping_path, mapping)
    console.print(f"\n  [green]✓[/green] Saved to {mapping_path}")

    # =========================================================================
    # Done
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print(
        Panel.fit(
            "[bold green]Data Mapping Complete![/bold green]\n\n"
            f"Configuration saved to: {mapping_path}\n\n"
            "[bold]Next Steps:[/bold]\n"
            "1. Review the mapping in data_mapping.yaml\n"
            "2. Restart the MCP server to apply changes\n"
            "3. Test with: [cyan]uavcrew check[/cyan]\n\n"
            "[dim]The MCP server will now query your tables using this mapping.[/dim]",
            border_style="green",
        )
    )


# =============================================================================
# Status Command
# =============================================================================

SERVICE_NAME = "mcp-server"


def _check_systemd_service() -> dict:
    """Check systemd service status. Returns dict with status info."""
    result = {
        "installed": False,
        "enabled": False,
        "running": False,
        "status": "not installed",
    }

    service_file = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
    if not service_file.exists():
        return result

    result["installed"] = True

    # Check if enabled
    try:
        proc = subprocess.run(
            ["systemctl", "is-enabled", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        result["enabled"] = proc.returncode == 0
    except Exception:
        pass

    # Check if running
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        result["running"] = proc.stdout.strip() == "active"
        result["status"] = proc.stdout.strip()
    except Exception:
        pass

    return result


def _check_process_running(port: int = 8200) -> dict:
    """Check if MCP server process is running (non-systemd)."""
    result = {
        "running": False,
        "pid": None,
        "method": None,
    }

    try:
        # Check if something is listening on the port
        proc = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
        )
        if f":{port}" in proc.stdout:
            result["running"] = True
            # Try to extract PID
            import re
            match = re.search(r'pid=(\d+)', proc.stdout)
            if match:
                result["pid"] = match.group(1)
            result["method"] = "manual"
    except Exception:
        pass

    return result


@app.command()
def status():
    """Check MCP server installation and service status."""
    console.print(
        Panel.fit(
            "[bold blue]UAVCrew MCP Server Status[/bold blue]",
            border_style="blue",
        )
    )

    env_path = Path.cwd() / ".env"

    # ==========================================================================
    # Configuration Status
    # ==========================================================================
    console.print("\n[bold]Configuration:[/bold]")

    config_ok = True
    port = 8200

    if env_path.exists():
        console.print(f"  [green]✓[/green] .env file exists")
        env_vars = load_env_file(env_path)

        # Check key variables
        if env_vars.get("DATABASE_URL"):
            console.print(f"  [green]✓[/green] DATABASE_URL configured")
        else:
            console.print(f"  [red]✗[/red] DATABASE_URL not set")
            config_ok = False

        # Check API keys (support both single and multiple)
        api_key = env_vars.get("MCP_API_KEY", "")
        api_keys = env_vars.get("MCP_API_KEYS", "")
        if api_key or api_keys:
            key_count = len([k for k in (api_key + "," + api_keys).split(",") if k.strip()])
            console.print(f"  [green]✓[/green] API key(s) configured ({key_count} key(s))")
        else:
            console.print(f"  [yellow]![/yellow] No API keys configured (server will be open)")

        port = int(env_vars.get("MCP_PORT", "8200"))
        public_url = env_vars.get("MCP_PUBLIC_URL", "")
        if public_url:
            console.print(f"  [dim]Public URL: {public_url}[/dim]")
    else:
        console.print(f"  [red]✗[/red] .env file not found")
        console.print(f"  [dim]Run 'uavcrew setup' to configure[/dim]")
        config_ok = False

    # ==========================================================================
    # Service Status
    # ==========================================================================
    console.print("\n[bold]Service Status:[/bold]")

    systemd = _check_systemd_service()
    process = _check_process_running(port)

    running = False
    restart_cmd = None

    if systemd["installed"]:
        console.print(f"  [green]✓[/green] Systemd service installed")

        if systemd["enabled"]:
            console.print(f"  [green]✓[/green] Service enabled (starts on boot)")
        else:
            console.print(f"  [yellow]![/yellow] Service not enabled")

        if systemd["running"]:
            console.print(f"  [green]✓[/green] Service running")
            running = True
            restart_cmd = f"sudo systemctl restart {SERVICE_NAME}"
        else:
            console.print(f"  [red]✗[/red] Service not running ({systemd['status']})")
            restart_cmd = f"sudo systemctl start {SERVICE_NAME}"
    else:
        console.print(f"  [dim]–[/dim] Systemd service not installed")

        # Check for manual process
        if process["running"]:
            console.print(f"  [green]✓[/green] Server running (manual, PID: {process['pid'] or 'unknown'})")
            running = True
            restart_cmd = f"# Kill PID {process['pid']} and restart manually"
        else:
            console.print(f"  [red]✗[/red] Server not running")

    # ==========================================================================
    # Summary & Next Steps
    # ==========================================================================
    console.print("\n[bold]Actions:[/bold]")

    if not config_ok:
        console.print(f"  → Run [cyan]uavcrew setup[/cyan] to configure the server")
    elif not systemd["installed"]:
        console.print(f"  → Run [cyan]uavcrew generate-systemd[/cyan] to create service")
        console.print(f"  → Or start manually: [cyan]mcp-http-server[/cyan]")
    elif not running:
        console.print(f"  → Start: [cyan]{restart_cmd}[/cyan]")
    else:
        console.print(f"  [green]Server is running and configured![/green]")
        if restart_cmd:
            console.print(f"  → Restart: [cyan]{restart_cmd}[/cyan]")
        console.print(f"  → Check config: [cyan]uavcrew check[/cyan]")
        console.print(f"  → View logs: [cyan]sudo journalctl -u {SERVICE_NAME} -f[/cyan]")


@app.command()
def setup():
    """Interactive setup wizard for UAVCrew MCP Server."""
    console.print(
        Panel.fit(
            "[bold blue]UAVCrew MCP Server Setup[/bold blue]\n\n"
            "This wizard will configure your MCP server to connect with UAVCrew.ai.\n"
            "Your flight data stays on your infrastructure - UAVCrew fetches only what\n"
            "it needs for compliance analysis.",
            border_style="blue",
        )
    )

    env_path = Path.cwd() / ".env"
    existing = {}

    # Load existing config if available
    if env_path.exists():
        existing = load_env_file(env_path)
        console.print("\n[yellow]Found existing .env file. Values will be used as defaults.[/yellow]")
        if not Confirm.ask("Continue with setup?", default=True):
            console.print("Setup cancelled.", style="yellow")
            raise typer.Exit(0)

    config = {}

    # =========================================================================
    # STEP 1: Server Identity & Access
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 1: Server Identity & Access[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nThese settings define how UAVCrew.ai will connect to your MCP server."
    )

    # Server name
    console.print("\n[bold]Server Name[/bold]")
    console.print("  A friendly name to identify this server in the UAVCrew dashboard.")
    console.print("  Examples: 'NYC Operations MCP', 'Acme Corp Flight Data', 'Production MCP'")
    config["MCP_SERVER_NAME"] = Prompt.ask(
        "\n  Server name",
        default=existing.get("MCP_SERVER_NAME", "MCP Server"),
    )

    # Public URL
    console.print("\n[bold]Public URL[/bold]")
    console.print("  The HTTPS URL where UAVCrew.ai can reach this server.")
    console.print("  This is your domain with HTTPS, NOT the local port.")
    console.print("  Examples: 'https://mcp.yourcompany.com', 'https://uav-data.example.org'")
    console.print("\n  [dim]You'll set up the reverse proxy (Caddy/Nginx) in a later step.[/dim]")
    config["MCP_PUBLIC_URL"] = Prompt.ask(
        "\n  Public URL",
        default=existing.get("MCP_PUBLIC_URL", "https://mcp.example.com"),
    )

    # Local binding
    console.print("\n[bold]Local Server Binding[/bold]")
    console.print("  The MCP server listens locally on this host:port.")
    console.print("  Your reverse proxy (Caddy/Nginx) will forward HTTPS traffic here.")
    config["MCP_HOST"] = Prompt.ask(
        "  Listen address",
        default=existing.get("MCP_HOST", "127.0.0.1"),
    )
    config["MCP_PORT"] = Prompt.ask(
        "  Listen port",
        default=existing.get("MCP_PORT", "8200"),
    )

    # =========================================================================
    # STEP 2: Database Configuration
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 2: Database Configuration[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nThe MCP server needs access to your flight data database.\n"
        "This can be your existing database or a dedicated one."
    )

    # Database type selection
    db_choices = list(DB_CONFIGS.keys())
    console.print("\n[bold]Available databases:[/bold]")
    for i, db in enumerate(db_choices, 1):
        note = "[green](built-in, good for testing)[/green]" if db == "sqlite" else ""
        console.print(f"  {i}. {db.title()} {note}")

    db_choice = Prompt.ask(
        "\n  Select database type",
        choices=[str(i) for i in range(1, len(db_choices) + 1)],
        default="1",
    )
    db_type = db_choices[int(db_choice) - 1]

    # Install driver if needed
    if not check_driver_installed(db_type):
        if Confirm.ask(f"  Install {db_type} driver?", default=True):
            if not install_driver(db_type):
                console.print("  Cannot proceed without database driver.", style="red")
                raise typer.Exit(1)
        else:
            console.print("  Cannot proceed without database driver.", style="red")
            raise typer.Exit(1)

    # Build database URL
    console.print(f"\n[bold]{db_type.title()} Connection Details:[/bold]")
    database_url = build_database_url(db_type, existing)

    # Test connection
    console.print("\n  Testing connection... ", end="")
    success, message = test_database_connection(database_url)
    if success:
        console.print("[green]OK[/green]")
    else:
        console.print("[red]FAILED[/red]")
        console.print(f"  Error: {message}", style="red")
        if not Confirm.ask("  Continue anyway?", default=False):
            raise typer.Exit(1)

    config["DATABASE_URL"] = database_url

    # =========================================================================
    # STEP 3: UAVCrew Connection Token
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 3: UAVCrew Connection Token[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nTo connect this MCP server to UAVCrew.ai, you need a connection token.\n"
    )
    console.print("[bold]To get your token:[/bold]")
    console.print("  1. Go to [link]https://www.uavcrew.ai/dashboard/mcp/[/link]")
    console.print("  2. Click [cyan]'Register MCP Server'[/cyan]")
    console.print(f"  3. Enter name: [cyan]{config['MCP_SERVER_NAME']}[/cyan]")
    console.print(f"  4. Enter URL: [cyan]{config['MCP_PUBLIC_URL']}[/cyan]")
    console.print("  5. Copy the connection token shown")
    console.print("\n[dim]The token starts with 'mcp_' and is shown only once.[/dim]")

    token = Prompt.ask(
        "\n  Connection token",
        default=existing.get("MCP_API_KEY", ""),
        password=True,
    )
    config["MCP_API_KEY"] = token

    if token:
        console.print("  [green]✓[/green] Token saved")
    else:
        console.print("  [yellow]![/yellow] No token provided - configure later in .env")

    # =========================================================================
    # STEP 4: Security & Options
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 4: Security & Options[/bold cyan]")
    console.print("=" * 60)

    # Secret key
    if not existing.get("SECRET_KEY"):
        config["SECRET_KEY"] = generate_secret_key()
        console.print("\n  [green]✓[/green] Generated SECRET_KEY")
    else:
        config["SECRET_KEY"] = existing["SECRET_KEY"]
        console.print("\n  [green]✓[/green] Using existing SECRET_KEY")

    # Demo data
    console.print("\n[bold]Demo Data[/bold]")
    console.print("  Seed sample flights, pilots, and aircraft for testing.")
    console.print("  [yellow]Disable this in production.[/yellow]")
    seed_demo = Confirm.ask(
        "  Seed demo data on startup?",
        default=existing.get("SEED_DEMO_DATA", "false").lower() == "true",
    )
    config["SEED_DEMO_DATA"] = str(seed_demo).lower()

    # =========================================================================
    # STEP 5: Write Configuration
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 5: Save Configuration[/bold cyan]")
    console.print("=" * 60)

    write_env_file(env_path, config)
    console.print(f"\n  [green]✓[/green] Configuration saved to {env_path}")

    # =========================================================================
    # STEP 6: Reverse Proxy Setup
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 6: Reverse Proxy Setup[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nA reverse proxy handles HTTPS and forwards requests to the MCP server.\n"
        "This makes your server accessible at your public URL with SSL encryption."
    )

    console.print("\n[bold]What reverse proxy do you use?[/bold]")
    console.print("  1. Caddy [green](recommended - automatic HTTPS)[/green]")
    console.print("  2. Nginx")
    console.print("  3. Apache")
    console.print("  4. None / I'll configure it myself")

    proxy_choice = Prompt.ask(
        "\n  Select option",
        choices=["1", "2", "3", "4"],
        default="1",
    )

    # Extract domain from public URL
    domain = config["MCP_PUBLIC_URL"].replace("https://", "").replace("http://", "").rstrip("/")

    if proxy_choice == "1":
        # Caddy
        caddy_config = generate_caddy_config(domain)
        console.print("\n[bold]Caddy Configuration:[/bold]")
        console.print(Panel(caddy_config, title="Add to /etc/caddy/Caddyfile"))
        console.print("\n[bold]To apply:[/bold]")
        console.print("  1. Add the above to your Caddyfile")
        console.print("  2. Run: [cyan]sudo systemctl reload caddy[/cyan]")
        console.print("\n  Caddy will automatically obtain and renew SSL certificates.")

        if Confirm.ask("\n  Save Caddy config to ./caddy-mcp.conf?", default=True):
            with open("caddy-mcp.conf", "w") as f:
                f.write(caddy_config)
            console.print("  [green]✓[/green] Saved to ./caddy-mcp.conf")

    elif proxy_choice == "2":
        # Nginx
        nginx_config = generate_nginx_config(domain)
        console.print("\n[bold]Nginx Configuration:[/bold]")
        console.print(Panel(nginx_config, title=f"/etc/nginx/sites-available/{domain}"))
        console.print("\n[bold]To apply:[/bold]")
        console.print(f"  1. Save to /etc/nginx/sites-available/{domain}")
        console.print(f"  2. Run: [cyan]sudo ln -s /etc/nginx/sites-available/{domain} /etc/nginx/sites-enabled/[/cyan]")
        console.print(f"  3. Get SSL cert: [cyan]sudo certbot --nginx -d {domain}[/cyan]")
        console.print("  4. Run: [cyan]sudo systemctl reload nginx[/cyan]")

        if Confirm.ask("\n  Save Nginx config to ./nginx-mcp.conf?", default=True):
            with open("nginx-mcp.conf", "w") as f:
                f.write(nginx_config)
            console.print("  [green]✓[/green] Saved to ./nginx-mcp.conf")

    elif proxy_choice == "3":
        # Apache
        apache_config = generate_apache_config(domain)
        console.print("\n[bold]Apache Configuration:[/bold]")
        console.print(Panel(apache_config, title=f"/etc/apache2/sites-available/{domain}.conf"))
        console.print("\n[bold]To apply:[/bold]")
        console.print("  1. Enable required modules: [cyan]sudo a2enmod proxy proxy_http ssl[/cyan]")
        console.print(f"  2. Save to /etc/apache2/sites-available/{domain}.conf")
        console.print(f"  3. Run: [cyan]sudo a2ensite {domain}[/cyan]")
        console.print(f"  4. Get SSL cert: [cyan]sudo certbot --apache -d {domain}[/cyan]")
        console.print("  5. Run: [cyan]sudo systemctl reload apache2[/cyan]")

        if Confirm.ask("\n  Save Apache config to ./apache-mcp.conf?", default=True):
            with open("apache-mcp.conf", "w") as f:
                f.write(apache_config)
            console.print("  [green]✓[/green] Saved to ./apache-mcp.conf")

    else:
        console.print("\n  Skipping reverse proxy configuration.")
        console.print(f"  Make sure to configure your proxy to forward {config['MCP_PUBLIC_URL']} to localhost:{config['MCP_PORT']}")

    # =========================================================================
    # STEP 7: Systemd Service
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]STEP 7: Systemd Service[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nA systemd service keeps the MCP server running and starts it on boot."
    )

    if Confirm.ask("\n  Generate and install systemd service?", default=True):
        _generate_systemd(env_path)

    # =========================================================================
    # DONE
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print(
        Panel.fit(
            "[bold green]Setup Complete![/bold green]\n\n"
            f"Server Name: {config['MCP_SERVER_NAME']}\n"
            f"Public URL:  {config['MCP_PUBLIC_URL']}\n"
            f"Local:       {config['MCP_HOST']}:{config['MCP_PORT']}\n\n"
            "[bold]Next Steps:[/bold]\n"
            "1. Configure your reverse proxy (see above)\n"
            "2. Start the service: [cyan]sudo systemctl start mcp-server[/cyan]\n"
            "3. Test the connection from UAVCrew dashboard\n\n"
            "[bold]Commands:[/bold]\n"
            "  [cyan]uavcrew check[/cyan]  - Validate configuration\n"
            "  [cyan]sudo systemctl status mcp-server[/cyan]  - Check service status",
            border_style="green",
        )
    )


def _run_check(env_path: Optional[Path] = None) -> bool:
    """Internal check implementation. Returns True if all checks pass."""
    if env_path is None:
        env_path = Path.cwd() / ".env"

    all_passed = True

    # Load .env if it exists
    from dotenv import load_dotenv

    load_dotenv(env_path)

    # Environment checks
    console.print("\n[bold]Environment:[/bold]")

    if env_path.exists():
        console.print("  [green]✓[/green] .env file exists")
    else:
        console.print("  [red]✗[/red] .env file not found")
        all_passed = False

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        console.print("  [green]✓[/green] DATABASE_URL set")
    else:
        console.print("  [red]✗[/red] DATABASE_URL not set")
        all_passed = False

    # Database checks
    console.print("\n[bold]Database:[/bold]")

    if db_url:
        # Detect database type from URL
        if db_url.startswith("sqlite"):
            db_type = "sqlite"
        elif db_url.startswith("postgresql"):
            db_type = "postgresql"
        elif db_url.startswith("mysql"):
            db_type = "mysql"
        elif db_url.startswith("mssql"):
            db_type = "sqlserver"
        elif db_url.startswith("oracle"):
            db_type = "oracle"
        else:
            db_type = "unknown"

        if check_driver_installed(db_type):
            driver = DB_CONFIGS.get(db_type, {}).get("driver", "built-in")
            console.print(f"  [green]✓[/green] Driver installed ({driver})")
        else:
            console.print(f"  [red]✗[/red] Driver not installed for {db_type}")
            all_passed = False

        success, message = test_database_connection(db_url)
        if success:
            console.print("  [green]✓[/green] Connection successful")

            # Check tables and data
            try:
                from sqlalchemy import create_engine, inspect, text

                engine = create_engine(db_url)
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                console.print(f"  [green]✓[/green] Tables exist ({len(tables)} tables)")

                # Count demo data
                with engine.connect() as conn:
                    pilots = conn.execute(text("SELECT COUNT(*) FROM pilots")).scalar()
                    aircraft = conn.execute(
                        text("SELECT COUNT(*) FROM aircraft")
                    ).scalar()
                    flights = conn.execute(text("SELECT COUNT(*) FROM flights")).scalar()
                if pilots > 0:
                    console.print(
                        f"  [green]✓[/green] Data present ({pilots} pilots, {aircraft} aircraft, {flights} flights)"
                    )
                else:
                    console.print("  [yellow]![/yellow] No data (run with SEED_DEMO_DATA=true)")
            except Exception as e:
                console.print(f"  [yellow]![/yellow] Could not inspect tables: {e}")
        else:
            console.print(f"  [red]✗[/red] Connection failed: {message}")
            all_passed = False

    # Security checks
    console.print("\n[bold]Security:[/bold]")

    api_key = os.environ.get("MCP_API_KEY")
    if api_key:
        # Mask the key for display
        masked = api_key[:8] + "****" if len(api_key) > 8 else "****"
        console.print(f"  [green]✓[/green] MCP_API_KEY configured ({masked})")
    else:
        console.print("  [yellow]![/yellow] MCP_API_KEY not set (server will accept any request)")

    seed_demo = os.environ.get("SEED_DEMO_DATA", "false").lower()
    if seed_demo == "true":
        console.print("  [yellow]![/yellow] SEED_DEMO_DATA=true (disable in production)")

    # Summary
    if all_passed:
        console.print("\n[bold green]All checks passed![/bold green]")
    else:
        console.print("\n[bold red]Some checks failed.[/bold red]")

    return all_passed


@app.command()
def check():
    """Validate current configuration."""
    console.print(
        Panel.fit(
            "[bold blue]UAVCrew MCP Server - Configuration Check[/bold blue]",
            border_style="blue",
        )
    )
    success = _run_check()
    raise typer.Exit(0 if success else 1)


def _generate_systemd(env_path: Optional[Path] = None):
    """Internal systemd generation."""
    if env_path is None:
        env_path = Path.cwd() / ".env"

    paths = detect_paths()

    # Show detected paths
    table = Table(title="Detected Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Working directory", str(paths["workdir"]))
    table.add_row("Python", str(paths["python"]))
    table.add_row("User", paths["user"])
    if paths["venv"]:
        table.add_row("Virtual environment", str(paths["venv"]))
    console.print(table)

    # Generate unit file
    unit_content = generate_systemd_unit(paths, env_path)

    console.print("\n[bold]Generated unit file:[/bold]")
    console.print(Panel(unit_content, title="mcp-server.service"))

    # Save options
    console.print("\n[bold]Where to save?[/bold]")
    console.print("  1. Install to /etc/systemd/system/ [green](recommended)[/green]")
    console.print("  2. Save to current directory")
    console.print("  3. Don't save")

    action = Prompt.ask("\n  Select action", choices=["1", "2", "3"], default="1")

    if action == "1":
        output_path = Path("/etc/systemd/system/mcp-server.service")
        try:
            # Try direct write first (if running as root)
            with open(output_path, "w") as f:
                f.write(unit_content)
        except PermissionError:
            # Fall back to sudo
            console.print("  Requires sudo privileges...", style="yellow")
            proc = subprocess.run(
                ["sudo", "tee", str(output_path)],
                input=unit_content.encode(),
                capture_output=True,
            )
            if proc.returncode != 0:
                console.print("  [red]✗[/red] Failed to write systemd unit file", style="red")
                console.print("  Try option 2 to save locally, then install manually.")
                return

        console.print(f"  [green]✓[/green] Installed to {output_path}")

        # Reload systemd
        try:
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True, capture_output=True)
            console.print("  [green]✓[/green] Reloaded systemd")
        except subprocess.CalledProcessError:
            console.print("  [yellow]![/yellow] Could not reload systemd")

        if Confirm.ask("\n  Enable service to start on boot?", default=True):
            try:
                subprocess.run(
                    ["sudo", "systemctl", "enable", "mcp-server"],
                    check=True,
                    capture_output=True,
                )
                console.print("  [green]✓[/green] Service enabled")
            except subprocess.CalledProcessError:
                console.print("  [yellow]![/yellow] Could not enable service")

        console.print("\n  [bold]To start now:[/bold] sudo systemctl start mcp-server")
        console.print("  [bold]To check status:[/bold] sudo systemctl status mcp-server")

    elif action == "2":
        output_path = Path.cwd() / "mcp-server.service"
        with open(output_path, "w") as f:
            f.write(unit_content)
        console.print(f"\n  [green]✓[/green] Saved to {output_path}")
        console.print("\n  [bold]To install manually:[/bold]")
        console.print(f"    sudo cp {output_path} /etc/systemd/system/")
        console.print("    sudo systemctl daemon-reload")
        console.print("    sudo systemctl enable --now mcp-server")

    else:
        console.print("\n  Skipped. Copy the unit file above manually if needed.")


@app.command("generate-systemd")
def generate_systemd():
    """Generate systemd unit file for the MCP server."""
    console.print(
        Panel.fit(
            "[bold blue]UAVCrew MCP Server - Systemd Generator[/bold blue]",
            border_style="blue",
        )
    )
    _generate_systemd()


if __name__ == "__main__":
    app()
