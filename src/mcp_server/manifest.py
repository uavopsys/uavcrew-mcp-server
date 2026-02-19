"""Manifest loader and validator for MCP Gateway.

Loads manifest.json which declares entities, their API paths, and available actions.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Required fields per entity
_REQUIRED_ENTITY_FIELDS = {"path", "id_field", "read"}

# Required fields per action
_REQUIRED_ACTION_FIELDS = {"method", "path"}

# Valid HTTP methods for actions
_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def load_manifest(path: str | None = None) -> dict[str, Any]:
    """Load and validate manifest.json.

    Args:
        path: Path to manifest.json. Defaults to MCP_MANIFEST_PATH env var
              or ./manifest.json.

    Returns:
        Validated manifest dict with keys: api_base_url, entities.

    Raises:
        FileNotFoundError: If manifest file doesn't exist.
        ValueError: If manifest is invalid.
    """
    if path is None:
        path = os.environ.get("MCP_MANIFEST_PATH", "./manifest.json")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        try:
            manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in manifest: {e}")

    _validate(manifest, path)

    logger.info(
        "Loaded manifest: %d entities from %s",
        len(manifest.get("entities", {})),
        path,
    )
    return manifest


def _validate(manifest: dict, path: str) -> None:
    """Validate manifest structure."""
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")

    # api_base_url
    if "api_base_url" not in manifest:
        raise ValueError("Manifest missing required field: api_base_url")

    base_url = manifest["api_base_url"]
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("api_base_url must be a non-empty string")

    # entities
    if "entities" not in manifest:
        raise ValueError("Manifest missing required field: entities")

    entities = manifest["entities"]
    if not isinstance(entities, dict) or not entities:
        raise ValueError("entities must be a non-empty object")

    for name, entity in entities.items():
        _validate_entity(name, entity)

    # auth (optional — defaults to static mode)
    _validate_auth(manifest)


def _validate_entity(name: str, entity: dict) -> None:
    """Validate a single entity definition."""
    if not isinstance(entity, dict):
        raise ValueError(f"Entity '{name}' must be an object")

    # Required fields
    missing = _REQUIRED_ENTITY_FIELDS - set(entity.keys())
    if missing:
        raise ValueError(f"Entity '{name}' missing required fields: {', '.join(sorted(missing))}")

    if not isinstance(entity["path"], str) or not entity["path"]:
        raise ValueError(f"Entity '{name}': path must be a non-empty string")

    if not isinstance(entity["read"], bool):
        raise ValueError(f"Entity '{name}': read must be a boolean")

    # Optional: search
    if "search" in entity and not isinstance(entity["search"], bool):
        raise ValueError(f"Entity '{name}': search must be a boolean")

    # Optional: actions
    if "actions" in entity:
        actions = entity["actions"]
        if not isinstance(actions, dict):
            raise ValueError(f"Entity '{name}': actions must be an object")

        for action_name, action in actions.items():
            _validate_action(name, action_name, action)


def _validate_action(entity_name: str, action_name: str, action: dict) -> None:
    """Validate a single action definition."""
    if not isinstance(action, dict):
        raise ValueError(f"Entity '{entity_name}' action '{action_name}' must be an object")

    missing = _REQUIRED_ACTION_FIELDS - set(action.keys())
    if missing:
        raise ValueError(
            f"Entity '{entity_name}' action '{action_name}' missing required fields: "
            f"{', '.join(sorted(missing))}"
        )

    method = action["method"]
    if method not in _VALID_METHODS:
        raise ValueError(
            f"Entity '{entity_name}' action '{action_name}': "
            f"method must be one of {_VALID_METHODS}, got '{method}'"
        )

    if not isinstance(action["path"], str) or not action["path"]:
        raise ValueError(
            f"Entity '{entity_name}' action '{action_name}': path must be a non-empty string"
        )


_VALID_AUTH_MODES = {"static", "dynamic"}


def _validate_auth(manifest: dict) -> None:
    """Validate the auth section of the manifest.

    If no auth key is present, injects a default static config for backward compat.
    """
    if "auth" not in manifest:
        # Default: static mode with CLIENT_API_TOKEN
        manifest["auth"] = {"mode": "static", "token_env": "CLIENT_API_TOKEN"}
        return

    auth = manifest["auth"]
    if not isinstance(auth, dict):
        raise ValueError("auth must be an object")

    mode = auth.get("mode")
    if mode not in _VALID_AUTH_MODES:
        raise ValueError(
            f"auth.mode must be one of {_VALID_AUTH_MODES}, got '{mode}'"
        )

    if mode == "static":
        token_env = auth.get("token_env")
        if not token_env or not isinstance(token_env, str):
            raise ValueError("auth.token_env must be a non-empty string for static mode")

    elif mode == "dynamic":
        resolver_path = auth.get("resolver_path")
        if not resolver_path or not isinstance(resolver_path, str):
            raise ValueError(
                "auth.resolver_path must be a non-empty string for dynamic mode"
            )
        if not resolver_path.startswith("/"):
            raise ValueError("auth.resolver_path must start with /")


def get_entity_names(manifest: dict) -> list[str]:
    """Get list of all entity names from manifest."""
    return list(manifest.get("entities", {}).keys())


def get_entity(manifest: dict, name: str) -> dict | None:
    """Get entity definition by name, or None if not found."""
    return manifest.get("entities", {}).get(name)


def get_entity_actions(manifest: dict, entity_name: str) -> dict:
    """Get available actions for an entity. Returns empty dict if none."""
    entity = get_entity(manifest, entity_name)
    if entity is None:
        return {}
    return entity.get("actions", {})
