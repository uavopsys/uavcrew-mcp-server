"""
Tests for manifest.json existence and completeness.

Ensures the manifest file exists, is valid JSON, and contains all
expected entities with their required fields and actions.
"""

import json
import os

import pytest


@pytest.fixture
def manifest():
    """Load the manifest file."""
    path = os.environ.get("MCP_MANIFEST_PATH", "./manifest.json")
    assert os.path.exists(path), f"manifest.json not found at {path}"
    with open(path) as f:
        return json.load(f)


# =============================================================================
# Structure
# =============================================================================


class TestManifestStructure:
    """Test manifest top-level structure."""

    def test_manifest_exists(self):
        path = os.environ.get("MCP_MANIFEST_PATH", "./manifest.json")
        assert os.path.exists(path), f"manifest.json not found at {path}"

    def test_has_api_base_url(self, manifest):
        assert "api_base_url" in manifest
        assert manifest["api_base_url"].startswith("http")

    def test_has_entities(self, manifest):
        assert "entities" in manifest
        assert isinstance(manifest["entities"], dict)
        assert len(manifest["entities"]) > 0

    def test_has_auth(self, manifest):
        assert "auth" in manifest
        assert "mode" in manifest["auth"]


# =============================================================================
# Expected entities
# =============================================================================


EXPECTED_ENTITIES = [
    "pilot",
    "aircraft",
    "flight",
    "mission",
    "maintenance",
    "checklist",
    "company",
    "service",
    "record",
    "crew",
    "parts",
    "fleet",
]


class TestManifestEntities:
    """Test all expected entities are present with required fields."""

    def test_all_entities_present(self, manifest):
        entities = manifest["entities"]
        for name in EXPECTED_ENTITIES:
            assert name in entities, f"Entity '{name}' missing from manifest"

    def test_no_artifact_entity(self, manifest):
        """artifact was renamed to record."""
        assert "artifact" not in manifest["entities"]

    def test_no_product_entity(self, manifest):
        """product was permanently removed."""
        assert "product" not in manifest["entities"]

    @pytest.mark.parametrize("entity_name", EXPECTED_ENTITIES)
    def test_entity_has_path(self, manifest, entity_name):
        entity = manifest["entities"][entity_name]
        assert "path" in entity, f"{entity_name} missing 'path'"
        assert entity["path"], f"{entity_name} has empty path"

    @pytest.mark.parametrize("entity_name", EXPECTED_ENTITIES)
    def test_entity_has_id_field(self, manifest, entity_name):
        entity = manifest["entities"][entity_name]
        assert "id_field" in entity, f"{entity_name} missing 'id_field'"

    @pytest.mark.parametrize("entity_name", EXPECTED_ENTITIES)
    def test_entity_has_read(self, manifest, entity_name):
        entity = manifest["entities"][entity_name]
        assert "read" in entity, f"{entity_name} missing 'read'"
        assert entity["read"] is True, f"{entity_name} should be readable"

    def test_company_is_singleton(self, manifest):
        company = manifest["entities"]["company"]
        assert company["id_field"] is None
        assert company.get("search") is False


# =============================================================================
# Checklist actions (Concord)
# =============================================================================


class TestChecklistEntity:
    """Test checklist entity has the actions Concord needs."""

    def test_checklist_path(self, manifest):
        checklist = manifest["entities"]["checklist"]
        assert checklist["path"] == "/checklists/"

    def test_checklist_has_actions(self, manifest):
        checklist = manifest["entities"]["checklist"]
        assert "actions" in checklist

    def test_checklist_create_action(self, manifest):
        actions = manifest["entities"]["checklist"]["actions"]
        assert "create" in actions
        assert actions["create"]["method"] == "POST"
        assert "templates" in actions["create"]["path"]

    def test_checklist_update_action(self, manifest):
        actions = manifest["entities"]["checklist"]["actions"]
        assert "update" in actions
        assert actions["update"]["method"] == "PATCH"
        assert "{id}" in actions["update"]["path"]

    def test_checklist_evaluate_action(self, manifest):
        actions = manifest["entities"]["checklist"]["actions"]
        assert "evaluate" in actions
        assert actions["evaluate"]["method"] == "POST"
        assert "{id}" in actions["evaluate"]["path"]
        assert "evaluate" in actions["evaluate"]["path"]


# =============================================================================
# Record entity
# =============================================================================


class TestRecordEntity:
    """Test record entity has the right structure."""

    def test_record_path(self, manifest):
        record = manifest["entities"]["record"]
        assert record["path"] == "/records/"

    def test_record_has_actions(self, manifest):
        record = manifest["entities"]["record"]
        assert "actions" in record

    def test_record_create_action(self, manifest):
        actions = manifest["entities"]["record"]["actions"]
        assert "create" in actions

    def test_record_update_action(self, manifest):
        actions = manifest["entities"]["record"]["actions"]
        assert "update" in actions

    def test_record_upload_action(self, manifest):
        actions = manifest["entities"]["record"]["actions"]
        assert "upload" in actions

    def test_record_download_url_action(self, manifest):
        actions = manifest["entities"]["record"]["actions"]
        assert "get_download_url" in actions


# =============================================================================
# Action structure validation
# =============================================================================


class TestActionStructure:
    """Test that all actions have required fields."""

    def test_all_actions_have_method_and_path(self, manifest):
        for entity_name, entity in manifest["entities"].items():
            for action_name, action in entity.get("actions", {}).items():
                assert "method" in action, (
                    f"{entity_name}.{action_name} missing 'method'"
                )
                assert "path" in action, f"{entity_name}.{action_name} missing 'path'"
                assert action["method"] in ("GET", "POST", "PATCH", "PUT", "DELETE"), (
                    f"{entity_name}.{action_name} has invalid method: {action['method']}"
                )
