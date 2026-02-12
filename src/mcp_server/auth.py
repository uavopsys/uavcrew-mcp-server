"""JWT validation for delegation tokens (T1/T2).

Validates tokens signed by UAVCrew (K2) using the public key (K3).
Extracts claims: tenant_id, scope, max_tier, agent, session_id.
See AUTH_DECISION.md for the full key/token reference.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import jwt  # PyJWT

logger = logging.getLogger(__name__)


@dataclass
class DelegationClaims:
    """Validated claims from a T1 delegation JWT."""

    tenant_id: str
    org_id: str
    agent: str  # e.g., "tucker" (extracted from sub "agent:tucker")
    scope: list[str] = field(default_factory=list)  # e.g., ["read:aircraft"]
    max_tier: str = "read_only"  # "read_only", "propose", "execute"
    session_id: str = ""
    jti: str = ""  # JWT ID for audit


def load_public_key(path: str) -> bytes | None:
    """Load K3 (RS256 public key) from file."""
    if not path:
        return None
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        logger.error("K3 public key not found: %s", path)
        return None


def validate_delegation_token(
    token: str, public_key: bytes
) -> DelegationClaims | None:
    """Validate a T1 delegation JWT and extract claims.

    Returns DelegationClaims on success, None on any failure (fail closed).
    """
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer="https://api.uavcrew.ai",
            audience="mcp-gateway",
            options={"require": ["exp", "iss", "aud", "sub"]},
        )

        # Require tenant_id claim
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            logger.warning("T1 missing tenant_id claim")
            return None

        sub = payload.get("sub", "")
        agent = sub.replace("agent:", "") if sub.startswith("agent:") else sub

        return DelegationClaims(
            tenant_id=tenant_id,
            org_id=payload.get("org_id", ""),
            agent=agent,
            scope=payload.get("scope", []),
            max_tier=payload.get("max_tier", "read_only"),
            session_id=payload.get("session_id", ""),
            jti=payload.get("jti", ""),
        )
    except jwt.ExpiredSignatureError:
        logger.warning("T1 expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("T1 validation failed: %s", e)
        return None
