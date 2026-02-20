"""Token resolver: resolves tenant_id → K4 (Client API token) on demand.

Two modes configured via manifest.json auth section:
  static:  Returns a fixed token from an env var (single-tenant deployments).
  dynamic: Calls client's resolver endpoint with T1 JWT (multi-tenant deployments).

Replaces tenant_db.py — no local storage, no sync, no drift.
See AUTH_DECISION.md for the full key/token reference.
"""

import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Timeout for resolver endpoint calls (seconds)
_RESOLVER_TIMEOUT = 10.0


@dataclass
class ResolveResult:
    """Result of a K4 token resolution attempt."""

    token: str | None
    reason: str  # "ok", "missing_env_var", "missing_jwt", "missing_tenant_id",
    #              "resolver_timeout", "resolver_connection_error",
    #              "resolver_http_NNN", "no_api_token_in_response", "not_configured"

    @property
    def ok(self) -> bool:
        return self.token is not None


class TokenResolver:
    """Resolves K4 tokens for tenant requests.

    Static mode: returns a fixed token from an environment variable.
    Dynamic mode: calls the client's resolver endpoint with the T1 JWT.
    """

    def __init__(self, auth_config: dict, api_base_url: str):
        """Initialize the token resolver from manifest auth config.

        Args:
            auth_config: The "auth" section from manifest.json.
                         Defaults to static mode with CLIENT_API_TOKEN if empty.
            api_base_url: Base URL of the client API (for building resolver URL).
        """
        self.mode = auth_config.get("mode", "static")
        self.resolver_url: str | None = None

        if self.mode == "static":
            env_var = auth_config.get("token_env", "CLIENT_API_TOKEN")
            self.token_env = env_var
            self.static_token = os.environ.get(env_var, "").strip() or None
        elif self.mode == "dynamic":
            resolver_path = auth_config.get("resolver_path", "")
            self.resolver_url = api_base_url.rstrip("/") + resolver_path
        else:
            raise ValueError(f"Unknown auth mode: {self.mode}")

    async def resolve(
        self, tenant_id: str | None = None, t1_jwt: str | None = None
    ) -> ResolveResult:
        """Resolve K4 for a tenant.

        Args:
            tenant_id: Tenant ID from T1 JWT claims. Required for dynamic mode.
            t1_jwt: Raw T1 JWT string. Used as Bearer auth for dynamic resolver.

        Returns:
            ResolveResult with token (or None) and a reason string.
        """
        if self.mode == "static":
            if self.static_token:
                return ResolveResult(self.static_token, "ok")
            return ResolveResult(None, "missing_env_var")

        if self.mode == "dynamic":
            if not t1_jwt:
                logger.warning(
                    "Dynamic resolver requires T1 JWT — legacy API key auth "
                    "cannot resolve K4 in dynamic mode"
                )
                return ResolveResult(None, "missing_jwt_for_dynamic_mode")

            if not tenant_id:
                logger.warning("Dynamic resolver requires tenant_id")
                return ResolveResult(None, "missing_tenant_id")

            try:
                async with httpx.AsyncClient(timeout=_RESOLVER_TIMEOUT) as client:
                    resp = await client.post(
                        self.resolver_url,
                        json={"tenant_id": tenant_id},
                        headers={"Authorization": f"Bearer {t1_jwt}"},
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("api_token")
                    if token:
                        logger.debug(
                            "Resolved K4 for tenant %s via %s",
                            tenant_id,
                            self.resolver_url,
                        )
                        return ResolveResult(token, "ok")
                    logger.warning(
                        "Resolver returned 200 but no api_token for tenant %s",
                        tenant_id,
                    )
                    return ResolveResult(None, "no_api_token_in_response")

                logger.warning(
                    "Resolver returned %d for tenant %s: %s",
                    resp.status_code,
                    tenant_id,
                    resp.text[:200],
                )
                return ResolveResult(None, f"resolver_http_{resp.status_code}")

            except httpx.TimeoutException:
                logger.error(
                    "Resolver timeout for tenant %s: %s",
                    tenant_id,
                    self.resolver_url,
                )
                return ResolveResult(None, "resolver_timeout")

            except httpx.RequestError as e:
                logger.error(
                    "Resolver request failed for tenant %s: %s",
                    tenant_id,
                    e,
                )
                return ResolveResult(None, "resolver_connection_error")

        return ResolveResult(None, "not_configured")
