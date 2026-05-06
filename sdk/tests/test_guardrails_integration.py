"""Integration tests for the GuardrailsClient — real HTTP calls, no mocks.

Run inside the Kind cluster via kubectl exec against the running registry API.
"""

import pytest

from tests.conftest import unique_name


@pytest.mark.integration
class TestGuardrailsCRUD:
    """Create, read, update, delete guardrails via the SDK client."""

    def test_create_guardrail(self, client):
        name = unique_name("gr-test")
        gr = client.guardrails.create(
            name=name,
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="block",
            config={"patterns": [{"pattern": r"\d{3}-\d{2}-\d{4}", "label": "ssn"}]},
        )
        assert gr.id is not None
        assert gr.name == name

    def test_list_guardrails_contains_created(self, client):
        name = unique_name("gr-list")
        client.guardrails.create(
            name=name,
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="warn",
            config={"patterns": [{"pattern": "test", "label": "test"}]},
        )
        guardrails = client.guardrails.list()
        assert any(g.name == name for g in guardrails)

    def test_get_guardrail_by_id(self, client):
        name = unique_name("gr-get")
        created = client.guardrails.create(
            name=name,
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="block",
            config={"patterns": [{"pattern": "test", "label": "test"}]},
        )
        fetched = client.guardrails.get(str(created.id))
        assert fetched.name == name
        assert str(fetched.id) == str(created.id)

    def test_update_guardrail(self, client):
        name = unique_name("gr-upd")
        created = client.guardrails.create(
            name=name,
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="warn",
            config={"patterns": [{"pattern": "test", "label": "test"}]},
        )
        updated = client.guardrails.update(
            str(created.id),
            description="Updated description",
        )
        assert updated.description == "Updated description"

    def test_delete_guardrail(self, client):
        name = unique_name("gr-del")
        created = client.guardrails.create(
            name=name,
            type="pre_processing",
            mechanism="regex",
            enforcement_mode="block",
            config={"patterns": [{"pattern": "test", "label": "test"}]},
        )
        client.guardrails.delete(str(created.id))
        # After deletion it should not appear in the list
        guardrails = client.guardrails.list()
        assert not any(str(g.id) == str(created.id) for g in guardrails)
