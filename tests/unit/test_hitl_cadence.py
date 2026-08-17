"""Kernel regression: one approval per run() call (HITL cadence)."""

from __future__ import annotations

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
from seasi_core.orchestration.runner import NeutralRunner, WorkflowStatus

TENANT = TenantScope(tenant_id="t", case_ref="two-gates")


def _approve(intent) -> ApprovalDecision:
    return ApprovalDecision(
        intent_id=intent.intent_id,
        approved=True,
        decided_by="h",
        decided_at=utc_now(),
    )


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="x.two-gates",
        revision=1,
        initial_state="s0",
        states=(
            StateSpec(name="s0"),
            StateSpec(name="s1"),
            StateSpec(name="s2"),
            StateSpec(name="done", terminal=True),
        ),
        transitions=(
            TransitionSpec(
                from_state="s0",
                to_state="s1",
                action=ActionCall(capability_id="x.dispatch1", input={"k": 1}),
            ),
            TransitionSpec(
                from_state="s1",
                to_state="s2",
                action=ActionCall(capability_id="x.dispatch2", input={"k": 2}),
            ),
            TransitionSpec(from_state="s2", to_state="done"),
        ),
    )


@pytest.fixture
def runner() -> NeutralRunner:
    reg = ActionRegistry()
    for i in (1, 2):
        reg.register(
            f"x.dispatch{i}",
            CapabilitySpec(
                capability_id=f"x.dispatch{i}",
                version="1.0.0",
                effect=EffectClass.EXTERNAL_MUTATION,
                approval=ApprovalPolicy.REQUIRED,
            ),
        )
    return NeutralRunner(reg)


def test_one_approval_per_call(runner: NeutralRunner) -> None:
    instance = runner.start(_definition(), TENANT)
    instance = runner.run(instance)  # pause at gate 1
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    instance = runner.run(instance, approver=_approve)  # gate 1 → pause at gate 2
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    assert instance.state == "s1"

    instance = runner.run(instance, approver=_approve)  # gate 2 → done
    assert instance.status is WorkflowStatus.COMPLETED
    assert instance.state == "done"


def test_single_gate_workflow_completes_in_one_approved_call() -> None:
    reg = ActionRegistry()
    reg.register(
        "x.only",
        CapabilitySpec(
            capability_id="x.only",
            version="1.0.0",
            effect=EffectClass.EXTERNAL_MUTATION,
            approval=ApprovalPolicy.REQUIRED,
        ),
    )
    wf = WorkflowDefinition(
        workflow_id="x.one-gate",
        revision=1,
        initial_state="a",
        states=(StateSpec(name="a"), StateSpec(name="b", terminal=True)),
        transitions=(
            TransitionSpec(
                from_state="a",
                to_state="b",
                action=ActionCall(capability_id="x.only", input={}),
            ),
        ),
    )
    runner = NeutralRunner(reg)
    instance = runner.start(wf, TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    instance = runner.run(instance, approver=_approve)
    assert instance.status is WorkflowStatus.COMPLETED


def test_run_is_not_reentrant(runner: NeutralRunner) -> None:
    """Dos run() concurrentes sobre la misma instancia: el segundo rechaza."""
    instance = runner.start(_definition(), TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    instance._executing = True  # simula un run activo en otro hilo
    try:
        from seasi_core.orchestration.runner import WorkflowError

        with pytest.raises(WorkflowError, match="not reentrant"):
            runner.run(instance, approver=_approve)
    finally:
        instance._executing = False

    # tras liberar, funciona normalmente
    instance = runner.run(instance, approver=_approve)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL


def test_expired_intent_fails_explicitly(runner: NeutralRunner) -> None:
    """Un intent expirado se reporta como failure_reason explicito."""
    from datetime import timedelta

    instance = runner.start(_definition(), TENANT)
    instance = runner.run(instance)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL

    # expirar el intent sellado
    intent = instance.pending_intent
    assert intent is not None
    expired = intent.model_copy(
        update={
            "created_at": utc_now() - timedelta(seconds=2000),
            "expires_at": utc_now() - timedelta(seconds=1000),
        }
    )
    instance.pending_intent = expired

    instance = runner.run(instance, approver=_approve)
    # fail-closed: queda pausado con approval.invalid (digest y expiracion verificadas)
    assert instance.status is WorkflowStatus.PAUSED_APPROVAL
    types = [e.event_type for e in instance.history]
    assert "approval.invalid" in types
