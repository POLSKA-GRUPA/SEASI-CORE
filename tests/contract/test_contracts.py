"""Contract tests: workflow definition invariants and shipped JSON schemas."""

import json
from pathlib import Path

import pytest

from seasi_core.contracts.capabilities import (
    ApprovalPolicy,
    CapabilitySpec,
    EffectClass,
)
from seasi_core.contracts.workflows import (
    ActionCall,
    StateSpec,
    TransitionSpec,
    WorkflowDefinition,
)
from seasi_core.kernel.registry import ActionRegistry

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "v1"


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="onboarding.review",
        revision=1,
        initial_state="draft",
        states=(
            StateSpec(name="draft"),
            StateSpec(name="review"),
            StateSpec(name="dispatched", terminal=True),
        ),
        transitions=(
            TransitionSpec(from_state="draft", to_state="review"),
            TransitionSpec(
                from_state="review",
                to_state="dispatched",
                action=ActionCall(capability_id="ledger.post", input={"k": "v"}),
            ),
        ),
    )


class TestWorkflowDefinition:
    def test_checksum_deterministic(self) -> None:
        assert _definition().checksum() == _definition().checksum()

    def test_checksum_sensitive_to_revision(self) -> None:
        a = _definition()
        b = _definition().model_copy(update={"revision": 2})
        assert a.checksum() != b.checksum()

    def test_initial_state_must_exist(self) -> None:
        with pytest.raises(ValueError):
            WorkflowDefinition(
                workflow_id="x.y",
                revision=1,
                initial_state="ghost",
                states=(StateSpec(name="a", terminal=True),),
            )

    def test_unknown_transition_state_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown state"):
            WorkflowDefinition(
                workflow_id="x.y",
                revision=1,
                initial_state="a",
                states=(StateSpec(name="a", terminal=True),),
                transitions=(TransitionSpec(from_state="a", to_state="ghost"),),
            )

    def test_needs_terminal_state(self) -> None:
        with pytest.raises(ValueError, match="terminal"):
            WorkflowDefinition(
                workflow_id="x.y",
                revision=1,
                initial_state="a",
                states=(StateSpec(name="a"),),
            )

    def test_assert_capabilities_registered(self) -> None:
        actions = ActionRegistry()
        actions.register(
            "ledger.post",
            CapabilitySpec(
                capability_id="ledger.post",
                version="1.0.0",
                effect=EffectClass.EXTERNAL_MUTATION,
                approval=ApprovalPolicy.REQUIRED,
            ),
        )
        _definition().assert_capabilities_registered(actions)  # ok
        actions2 = ActionRegistry()
        with pytest.raises(ValueError, match="unknown capabilities"):
            _definition().assert_capabilities_registered(actions2)


class TestShippedSchemas:
    def _load(self, name: str) -> dict:
        path = SCHEMAS / name
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("additionalProperties") is False, f"{name} not closed"
        return data

    def test_tenant_scope_schema(self) -> None:
        schema = self._load("tenant-scope.schema.json")
        props = set(schema["properties"])
        assert props == {"tenant_id", "case_ref", "project_ref"}
        assert schema["required"] == ["tenant_id"]

    def test_approval_intent_schema(self) -> None:
        schema = self._load("approval-intent.schema.json")
        props = set(schema["properties"])
        assert props == {
            "intent_id",
            "tenant",
            "actor",
            "capability_id",
            "payload_digest",
            "created_at",
            "expires_at",
            "nonce",
        }
        assert set(schema["required"]) == props

    def test_event_envelope_schema(self) -> None:
        schema = self._load("event-envelope.schema.json")
        props = set(schema["properties"])
        assert props == {
            "event_id",
            "schema_version",
            "event_type",
            "tenant",
            "occurred_at",
            "correlation_id",
            "causation_id",
            "payload",
            "payload_digest",
        }
        assert schema["properties"]["schema_version"]["const"] == "seasi.event/v1"

    def test_schemas_exist(self) -> None:
        names = {p.name for p in SCHEMAS.glob("*.schema.json")}
        assert names == {
            "tenant-scope.schema.json",
            "approval-intent.schema.json",
            "event-envelope.schema.json",
        }
