"""Tests for API client: error sanitization and HTTP request handling."""

import pytest
import httpx
import respx

from mcp_server.api_client import ApiClient, _sanitize_error_details


class TestSanitizeErrorDetails:
    """Test HTML stripping and truncation of error details."""

    def test_html_error_page_stripped(self):
        """Full HTML error page should be stripped to text content."""
        html = """<!DOCTYPE html>
<html>
<head><title>Not Found</title></head>
<body>
<h1>Not Found</h1>
<p>The requested resource was not found on this server.</p>
</body>
</html>"""
        result = _sanitize_error_details(html)
        assert "<html" not in result
        assert "<body" not in result
        assert "<h1>" not in result
        assert "Not Found" in result

    def test_json_dict_preserved(self):
        """Dict details (from response.json()) should pass through unchanged."""
        details = {"error": "Not found", "code": 404}
        result = _sanitize_error_details(details)
        assert result == details

    def test_plain_text_preserved(self):
        """Plain text error message should pass through."""
        text = "Connection refused by upstream server"
        result = _sanitize_error_details(text)
        assert result == text

    def test_long_text_truncated(self):
        """Strings longer than 500 chars should be truncated."""
        long_text = "x" * 1000
        result = _sanitize_error_details(long_text)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    def test_empty_html_fallback(self):
        """HTML with no text content should return fallback message."""
        html = "<html><body></body></html>"
        result = _sanitize_error_details(html)
        assert result == "HTML error page (no extractable text)"

    def test_django_debug_page_stripped(self):
        """Django debug 404 page (large HTML) should be stripped and truncated."""
        html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Page not found at /api/v1/services/</title></head>
<body>
<div id="summary">
  <h1>Page not found <span>(404)</span></h1>
  <table class="meta"><tr><th>Request Method:</th><td>GET</td></tr>
  <tr><th>Request URL:</th><td>https://app.ayna.com/api/v1/services/</td></tr></table>
</div>
<div id="info">
  <p>Using the URLconf defined in <code>config.urls</code>, Django tried these URL patterns...</p>
  <p>The current path, <code>api/v1/services/</code>, didn't match any of these.</p>
</div>
</body>
</html>"""
        result = _sanitize_error_details(html)
        assert "<html" not in result
        assert "<div" not in result
        assert "Page not found" in result
        assert len(result) <= 503  # max 500 + "..."


class TestApiClientRequests:
    """Test actual HTTP request handling with K4 bearer token."""

    @pytest.mark.anyio
    @respx.mock
    async def test_get_sends_bearer_token(self):
        """K4 is sent as Authorization: Bearer header."""
        client = ApiClient("https://api.example.com/api/v1")

        route = respx.get("https://api.example.com/api/v1/pilots").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        await client.get("/pilots", "my-k4-token")

        assert route.called
        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer my-k4-token"

    @pytest.mark.anyio
    @respx.mock
    async def test_get_success_returns_data(self):
        """200 response → {success: true, data: ..., status_code: 200}."""
        client = ApiClient("https://api.example.com")

        respx.get("https://api.example.com/pilots/P-42").mock(
            return_value=httpx.Response(
                200, json={"id": "P-42", "name": "Test Pilot"}
            )
        )

        result = await client.get("/pilots/P-42", "k4")
        assert result["success"] is True
        assert result["data"]["id"] == "P-42"
        assert result["status_code"] == 200

    @pytest.mark.anyio
    @respx.mock
    async def test_get_error_returns_details(self):
        """404 response → {success: false, error: ..., details: ...}."""
        client = ApiClient("https://api.example.com")

        respx.get("https://api.example.com/pilots/unknown").mock(
            return_value=httpx.Response(
                404, json={"error": "Pilot not found"}
            )
        )

        result = await client.get("/pilots/unknown", "k4")
        assert result["success"] is False
        assert result["status_code"] == 404
        assert "details" in result

    @pytest.mark.anyio
    @respx.mock
    async def test_post_sends_json_body(self):
        """POST sends params as JSON body."""
        client = ApiClient("https://api.example.com")

        route = respx.post("https://api.example.com/pilots").mock(
            return_value=httpx.Response(201, json={"id": "P-99"})
        )

        await client.post("/pilots", "k4", params={"name": "New Pilot"})

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "New Pilot"

    @pytest.mark.anyio
    @respx.mock
    async def test_timeout_returns_504(self):
        """Request timeout → {success: false, status_code: 504}."""
        client = ApiClient("https://api.example.com", timeout=1.0)

        respx.get("https://api.example.com/slow").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await client.get("/slow", "k4")
        assert result["success"] is False
        assert result["status_code"] == 504
        assert "timed out" in result["error"].lower()

    @pytest.mark.anyio
    @respx.mock
    async def test_connection_error_returns_502(self):
        """Connection refused → {success: false, status_code: 502}."""
        client = ApiClient("https://api.example.com")

        respx.get("https://api.example.com/down").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        result = await client.get("/down", "k4")
        assert result["success"] is False
        assert result["status_code"] == 502

    def test_url_construction(self):
        """Base URL + path are concatenated correctly."""
        client = ApiClient("https://api.example.com/api/v1/")
        # Trailing slash should be stripped
        assert client.base_url == "https://api.example.com/api/v1"

    @pytest.mark.anyio
    @respx.mock
    async def test_get_with_query_params(self):
        """GET sends query parameters."""
        client = ApiClient("https://api.example.com")

        route = respx.get("https://api.example.com/pilots").mock(
            return_value=httpx.Response(200, json=[])
        )

        await client.get("/pilots", "k4", query={"limit": 10, "status": "active"})

        request = route.calls[0].request
        assert "limit=10" in str(request.url)
        assert "status=active" in str(request.url)
