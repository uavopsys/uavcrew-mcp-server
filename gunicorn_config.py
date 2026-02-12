# Gunicorn configuration for MCP Gateway
# Usage: gunicorn -c gunicorn_config.py mcp_server.server:app
import os

# Server socket
bind = os.environ.get("MCP_HOST", "127.0.0.1") + ":" + os.environ.get("MCP_PORT", "8200")
backlog = 2048

# Worker processes — ASGI via uvicorn worker
workers = 4
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
