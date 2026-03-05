# ---- Build stage ----
FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /build/dist

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/uavopsys/uavcrew-mcp-server"
LABEL org.opencontainers.image.description="UAVCrew MCP Gateway"

WORKDIR /app

# Install the wheel from build stage
COPY --from=build /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Gunicorn config is not included in the wheel
COPY gunicorn_config.py .

# Docker context — switches gunicorn to stdout/stderr logging
ENV MCP_DOCKER=1

# Default config paths (customers mount volumes here)
ENV MCP_MANIFEST_PATH=/app/config/manifest.json
ENV MCP_JWT_PUBLIC_KEY_PATH=/app/config/keys/k3_public.pem

# Bind to all interfaces inside the container
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8400

EXPOSE 8400

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8400/health')" || exit 1

CMD ["gunicorn", "--config", "gunicorn_config.py", "mcp_server.server:app"]
