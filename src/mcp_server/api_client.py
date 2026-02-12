"""HTTP client for calling client APIs.

Translates MCP tool calls into HTTP requests against the client's REST API,
using tenant-specific authentication tokens.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default timeout for API requests (seconds)
DEFAULT_TIMEOUT = 30.0


class ApiClient:
    """HTTP client for making authenticated requests to client APIs."""

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        """Initialize API client.

        Args:
            base_url: Base URL for the client API (e.g., "https://api.client.com/api/v1").
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to the client API.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.).
            path: API path (e.g., "/pilots/P-42"). Appended to base_url.
            token: Bearer token for authentication.
            params: JSON body for POST/PATCH/PUT requests.
            query: Query parameters for GET requests.

        Returns:
            Standardized response dict:
              {"success": True, "data": ..., "status_code": 200}
              {"success": False, "error": "...", "status_code": 500, "details": ...}
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=params if method in ("POST", "PATCH", "PUT") else None,
                    params=query if method == "GET" else None,
                )

            # Success (2xx)
            if 200 <= response.status_code < 300:
                try:
                    data = response.json()
                except Exception:
                    data = response.text
                return {
                    "success": True,
                    "data": data,
                    "status_code": response.status_code,
                }

            # Client/server error (4xx/5xx)
            try:
                details = response.json()
            except Exception:
                details = response.text

            error_msg = f"Client API returned {response.status_code}"
            logger.warning("%s: %s %s → %s", error_msg, method, url, details)

            return {
                "success": False,
                "error": error_msg,
                "status_code": response.status_code,
                "details": details,
            }

        except httpx.TimeoutException:
            logger.error("Timeout: %s %s (%.0fs)", method, url, self.timeout)
            return {
                "success": False,
                "error": f"Request timed out after {self.timeout}s",
                "status_code": 504,
            }

        except httpx.ConnectError as e:
            logger.error("Connection failed: %s %s → %s", method, url, e)
            return {
                "success": False,
                "error": f"Connection failed: {e}",
                "status_code": 502,
            }

        except httpx.RequestError as e:
            logger.error("Request error: %s %s → %s", method, url, e)
            return {
                "success": False,
                "error": f"Request error: {e}",
                "status_code": 500,
            }

    async def get(
        self, path: str, token: str, query: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET request."""
        return await self.request("GET", path, token, query=query)

    async def post(
        self, path: str, token: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST request."""
        return await self.request("POST", path, token, params=params)

    async def patch(
        self, path: str, token: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """PATCH request."""
        return await self.request("PATCH", path, token, params=params)
