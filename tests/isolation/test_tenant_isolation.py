"""Isolation tests: no data or authority crosses tenants."""

from datetime import timedelta

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

TENANT_A = TenantScope(tenant_id="acme", case_ref="case-a")
TENANT_B = TenantScope(tenant_id="beta", case_ref="case-b")


def _registry() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register(
        "ledger.post",
        CapabilitySpec(
            capability_id="ledger.post",
            version="1.0.0",
            effect=EffectClass.EXTERNAL_MUTATION,
            approval=ApprovalPolicy.REQUIRED,
        ),
    )
    reg.register(
        "docs.read",
        CapabilitySpec(capability_id="docs.read", version="1.0.0", effect=EffectClass.READ),
    )
    return reg


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="iso.dispatch",
        revision=1,
        initial_state="review",
        states=(StateSpec(name="review"), StateSpec(name="done", terminal=True)),
        transitions=(
            TransitionSpec(
                from_state="review",
                to_state="done",
                action=ActionCall(capability_id="ledger.post", input={"doc": "d1"}),
            ),
        ),
    )


def _approver_for(tenant: TenantScope):
    """Simulated human approving whatever intent the kernel produced."""

    def approve(intent):
        return ApprovalDecision(
            intent_id=intent.intent_id,
            approved=True,
            decided_by=f"reviewer@{tenant.tenant_id}",
            decided_at=utc_now(),
        )

    return approve


def test_events_carry_only_own_tenant() -> None:
    for tenant in (TENANT_A, TENANT_B):
        runner = NeutralRunner(_registry())
        instance = runner.start(_definition(), tenant)
        runner.run(instance, _approver_for(tenant))
        assert instance.status is WorkflowStatus.COMPLETED
        for event in instance.history:
            assert event.tenant.tenant_id == tenant.tenant_id


def test_pending_intent_is_sealed_to_its_tenant() -> None:
    runner = NeutralRunner(_registry())
    instance = runner.start(_definition(), TENANT_A)
    instance = runner.run(instance)  # pauses requesting approval
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    assert instance.pending_intent is not None
    assert instance.pending_intent.tenant.tenant_id == "acme"
    # The sealed digest binds tenant acme; verification for tenant beta
    # would fail (covered in unit/test_intent_binding cross-tenant case).
    remaining = instance.pending_intent.expires_at - utc_now()
    assert timedelta(0) < remaining < timedelta(seconds=1000)


def test_instances_are_independent() -> None:
    runner = NeutralRunner(_registry())
    ia = runner.start(_definition(), TENANT_A, data={"secret": "a"})
    ib = runner.start(_definition(), TENANT_B, data={"secret": "b"})
    runner.run(ia, _approver_for(TENANT_A))
    runner.run(ib, _approver_for(TENANT_B))
    assert ia.data["secret"] == "a" and ib.data["secret"] == "b"
    assert ia.history is not ib.history


def test_handler_receives_only_its_tenant_scope() -> None:
    seen: list[TenantScope] = []

    def handler(tenant: TenantScope, capability_id: str, payload):
        seen.append(tenant)
        return {"handled_by": tenant.tenant_id}

    runner = NeutralRunner(_registry(), handlers={"ledger.post": handler})
    instance = runner.start(_definition(), TENANT_A)
    runner.run(instance, _approver_for(TENANT_A))
    assert instance.status is WorkflowStatus.COMPLETED
    assert seen == [TENANT_A]
    assert instance.data["handled_by"] == "acme"
