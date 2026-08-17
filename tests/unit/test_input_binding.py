"""``ActionCall.input_from``: declarative data flow between workflow steps.

Three invariants:
- a step receives the *real* output of previous steps, not static literals;
- a missing binding path fails the workflow (fail-closed), never dispatches;
- for governed effects the sealed digest covers resolved values, so
  mutating the underlying data after sealing breaks verification.
"""

from __future__ import annotations

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
from seasi_core.orchestration.runner import NeutralRunner, WorkflowStatus

TENANT = TenantScope(tenant_id="t", case_ref="binding")


def _approve(intent) -> ApprovalDecision:
    return ApprovalDecision(
        intent_id=intent.intent_id,
        approved=True,
        decided_by="h",
        decided_at=utc_now(),
    )


def _registry(*, gated_post: bool = False) -> ActionRegistry:
    actions = ActionRegistry()
    actions.register(
        "b.extract",
        CapabilitySpec(
            capability_id="b.extract",
            version="1.0.0",
            effect=EffectClass.READ,
            approval=ApprovalPolicy.NEVER,
        ),
    )
    actions.register(
        "b.post",
        CapabilitySpec(
            capability_id="b.post",
            version="1.0.0",
            effect=EffectClass.EXTERNAL_MUTATION if gated_post else EffectClass.LOCAL_DRAFT,
            approval=ApprovalPolicy.REQUIRED if gated_post else ApprovalPolicy.NEVER,
        ),
    )
    return actions


def _definition(binding_path: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="b.flow",
        revision=1,
        initial_state="s0",
        states=(StateSpec(name="s0"), StateSpec(name="s1"), StateSpec(name="done", terminal=True)),
        transitions=(
            TransitionSpec(
                from_state="s0",
                to_state="s1",
                action=ActionCall(capability_id="b.extract", input={"doc": "invoice.txt"}),
            ),
            TransitionSpec(
                from_state="s1",
                to_state="done",
                action=ActionCall(
                    capability_id="b.post",
                    input={"ledger": "main"},
                    input_from={"amount": binding_path},
                ),
            ),
        ),
    )


def test_step_consumes_previous_step_output() -> None:
    seen: dict[str, object] = {}

    def extract(tenant, capability_id, action_input):
        return {"extraction": {"total": "225.50"}}

    def post(tenant, capability_id, action_input):
        seen.update(action_input)
        return {"posted": True}

    runner = NeutralRunner(_registry(), handlers={"b.extract": extract, "b.post": post})
    instance = runner.run(runner.start(_definition("extraction.total"), TENANT))

    assert instance.status is WorkflowStatus.COMPLETED
    assert seen == {"ledger": "main", "amount": "225.50"}


def test_missing_binding_path_fails_closed() -> None:
    dispatched: list[str] = []

    def extract(tenant, capability_id, action_input):
        return {"extraction": {}}  # no 'total' produced

    def post(tenant, capability_id, action_input):
        dispatched.append(capability_id)
        return {}

    runner = NeutralRunner(_registry(), handlers={"b.extract": extract, "b.post": post})
    instance = runner.run(runner.start(_definition("extraction.total"), TENANT))

    assert instance.status is WorkflowStatus.FAILED
    assert "extraction.total" in (instance.failure_reason or "")
    assert dispatched == []


def test_governed_digest_seals_resolved_values() -> None:
    executed: list[str] = []

    def extract(tenant, capability_id, action_input):
        return {"extraction": {"total": "225.50"}}

    def post(tenant, capability_id, action_input):
        executed.append(capability_id)
        return {}

    runner = NeutralRunner(
        _registry(gated_post=True), handlers={"b.extract": extract, "b.post": post}
    )
    instance = runner.run(runner.start(_definition("extraction.total"), TENANT))
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    # Tamper with the bound data after the intent was sealed: the resolved
    # payload no longer matches the digest the human approved.
    instance.data["extraction"]["total"] = "999999.99"
    instance = runner.run(instance, approver=_approve)

    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    assert executed == []


def test_governed_binding_executes_after_clean_approval() -> None:
    executed: dict[str, object] = {}

    def extract(tenant, capability_id, action_input):
        return {"extraction": {"total": "225.50"}}

    def post(tenant, capability_id, action_input):
        executed.update(action_input)
        return {}

    runner = NeutralRunner(
        _registry(gated_post=True), handlers={"b.extract": extract, "b.post": post}
    )
    instance = runner.run(runner.start(_definition("extraction.total"), TENANT))
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    instance = runner.run(instance, approver=_approve)
    assert instance.status is WorkflowStatus.COMPLETED
    assert executed["amount"] == "225.50"
