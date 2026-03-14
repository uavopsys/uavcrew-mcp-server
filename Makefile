# UAVCrew MCP Gateway — Developer Commands
#
#   make dev       Start gateway in dev mode (gunicorn --reload)
#   make test      Run tests
#   make lint      Run linter
#   make clean     Clean build artifacts

.PHONY: dev test lint clean

# --- Dev server (venv, live reload) ---

dev:
	venv/bin/gunicorn --config gunicorn_config.py --reload mcp_server.server:app

# --- Tests & linting ---

test:
	venv/bin/pytest tests/ -v

lint:
	venv/bin/ruff check .

# --- Cleanup ---

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage dist/ build/ *.egg-info/
