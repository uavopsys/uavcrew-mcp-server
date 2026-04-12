"""
Validate MCP manifest against Django API conventions.
Run: python test_manifest.py
"""

import json
import sys


def test_manifest():
    with open("manifest.json") as f:
        m = json.load(f)

    errors = []

    for entity, config in m.get("entities", {}).items():
        # Base path must end with /
        base_path = config.get("path", "")
        if base_path and not base_path.endswith("/"):
            errors.append(f"{entity}: base path '{base_path}' missing trailing slash")

        for action, aconfig in config.get("actions", {}).items():
            path = aconfig.get("path", "")
            method = aconfig.get("method", "")

            # ALL action paths must end with / (Django APPEND_SLASH)
            if not path.endswith("/"):
                errors.append(
                    f"{entity}.{action}: {method} '{path}' missing trailing slash — "
                    f"Django APPEND_SLASH will reject {method} without slash"
                )

    if errors:
        print(f"FAILED: {len(errors)} issues found:\n")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    else:
        print(f"OK: all paths valid ({len(m.get('entities', {}))} entities checked)")
        return 0


if __name__ == "__main__":
    sys.exit(test_manifest())
