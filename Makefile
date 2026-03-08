# UAVCrew MCP Gateway — Developer Commands
# Port: 8400
#
#   make up        Start MCP gateway (Docker, live reload)
#   make down      Stop MCP gateway
#   make restart   Restart MCP gateway
#   make logs      Tail MCP gateway logs
#   make build     Build production Docker image (for distribution)
#   make rebuild   Rebuild dev image + recreate container
#   make clean     Clean build artifacts

COMPOSE := docker compose -f docker-compose.dev.yml
IMAGE   := ghcr.io/uavopsys/uavcrew-mcp-server

.PHONY: up down restart logs build rebuild clean

# --- Docker dev (live reload via volume mount) ---

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart mcp-gateway

logs:
	$(COMPOSE) logs -f mcp-gateway

rebuild:
	$(COMPOSE) up -d --build --force-recreate

# --- Production image (for distribution) ---

build:
	docker build -t $(IMAGE):dev .

clean:
	$(COMPOSE) down -v 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage dist/ build/ *.egg-info/
