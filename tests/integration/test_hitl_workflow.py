"""Integration: full HITL flow on the neutral runner.

Workflow under test (all synthetic, zero external effects):

    intake -> extract -> review --(approval gate)--> dispatch -> done

- extraction is a LOCAL_DRAFT capability (runs inline);
- dispatch is an EXTERNAL_MUTATION (pauses until a human approves);
- tampering with the approved payload must block execution;
- rejection terminates as FAILED with an audit trail;
- re-running a completed instance is a no-op.
"""

from __future__ import annotations

from typing import Any

import pytest

from seasi_core.contracts.capabilities import (
    ApprovalPolicy,
    CapabilitySpec,
    EffectClass,
)
from seasi_core.contracts.events import utc_now
from seasi_core.contracts.evidence import ApprovalDecision
from seasi_core.contracts.tenant import TenantScope
from seasi_core.contracts.workflows import (
    ActionCall,
    StateSpec,
    TransitionSpec,
    WorkflowDefinition,
)
from seasi_core.kernel.registry import ActionRegistry
from seasi_core.orchestration.runner import EventSink, NeutralRunner, WorkflowStatus

TENANT = TenantScope(tenant_id="acme", case_ref="case-42")


def _capabilities() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register(
        "intake.extract",
        CapabilitySpec(
            capability_id="intake.extract",
            version="1.0.0",
            effect=EffectClass.LOCAL_DRAFT,
        ),
    )
    reg.register(
        "ledger.dispatch",
        CapabilitySpec(
            capability_id="ledger.dispatch",
            version="1.0.0",
            effect=EffectClass.EXTERNAL_MUTATION,
            approval=ApprovalPolicy.REQUIRED,
            idempotent=True,
        ),
    )
    return reg


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="case.intake",
        revision=1,
        initial_state="intake",
        states=(
            StateSpec(name="intake"),
            StateSpec(name="extracted"),
            StateSpec(name="reviewed"),
            StateSpec(name="dispatched"),
            StateSpec(name="done", terminal=True),
        ),
        transitions=(
            TransitionSpec(
                from_state="intake",
                to_state="extracted",
                action=ActionCall(
                    capability_id="intake.extract",
                    input={"source": "upload://doc-1"},
                ),
            ),
            TransitionSpec(from_state="extracted", to_state="reviewed"),
            TransitionSpec(
                from_state="reviewed",
                to_state="dispatched",
                action=ActionCall(
                    capability_id="ledger.dispatch",
                    input={"entry": "draft-7", "amount": "225.50"},
                ),
            ),
            TransitionSpec(from_state="dispatched", to_state="done"),
        ),
    )


def _approve(intent) -> ApprovalDecision:
    return ApprovalDecision(
        intent_id=intent.intent_id,
        approved=True,
        decided_by="senior-reviewer",
        decided_at=utc_now(),
    )


def test_full_flow_with_approval() -> None:
    sink = EventSink()
    calls: list[dict[str, Any]] = []

    def extract_handler(tenant, capability_id, payload):
        calls.append({"cap": capability_id, "payload": dict(payload)})
        return {"extraction_id": "ext-1"}

    runner = NeutralRunner(
        _capabilities(),
        sink=sink,
        handlers={"intake.extract": extract_handler},
    )
    instance = runner.start(_workflow(), TENANT)
    instance = runner.run(instance)

    # paused at the governed transition
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    assert instance.pending_intent is not None
    assert instance.pending_intent.capability_id == "ledger.dispatch"

    instance = runner.run(instance, approver=_approve)
    assert instance.status is WorkflowStatus.COMPLETED
    assert instance.state == "done"

    types = [e.event_type for e in sink.events]
    assert "workflow.started" in types
    assert "action.dispatched" in types
    assert "approval.requested" in types
    assert "approval.granted" in types
    assert "transition.applied" in types
    assert "workflow.completed" in types

    # inline handler ran for the draft effect only
    assert calls and calls[0]["cap"] == "intake.extract"

    # re-run of a completed instance is a no-op (idempotent surface)
    events_before = len(sink.events)
    runner.run(instance, approver=_approve)
    assert len(sink.events) == events_before


def test_rejection_fails_with_audit() -> None:
    runner = NeutralRunner(_capabilities())
    instance = runner.start(_workflow(), TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    def reject(intent):
        return ApprovalDecision(
            intent_id=intent.intent_id,
            approved=False,
            decided_by="senior-reviewer",
            decided_at=utc_now(),
            note="amount mismatch",
        )

    instance = runner.run(instance, approver=reject)
    assert instance.status is WorkflowStatus.FAILED
    assert instance.failure_reason is not None
    assert "rejected" in instance.failure_reason
    types = [e.event_type for e in instance.history]
    assert "approval.rejected" in types
    assert "workflow.failed" in types


def test_tampered_payload_blocks_execution() -> None:
    runner = NeutralRunner(_capabilities())
    instance = runner.start(_workflow(), TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    # mutate the governed input AFTER the intent was sealed
    assert instance.pending_transition is not None
    tampered = instance.pending_transition.model_copy(
        update={"action": ActionCall(capability_id="ledger.dispatch", input={"amount": "9.99"})}
    )
    instance.pending_transition = tampered

    instance = runner.run(instance, approver=_approve)
    # digest no longer matches: invalid approval, stays paused, never executes
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    types = [e.event_type for e in instance.history]
    assert "approval.invalid" in types
    assert "approval.granted" not in types


def test_unknown_capability_fails_at_start() -> None:
    empty = ActionRegistry()
    runner = NeutralRunner(empty)
    with pytest.raises(ValueError, match="unknown capabilities"):
        runner.start(_workflow(), TENANT)


def test_no_approver_keeps_paused() -> None:
    runner = NeutralRunner(_capabilities())
    instance = runner.start(_workflow(), TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    instance = runner.run(instance)  # no approver provided
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
