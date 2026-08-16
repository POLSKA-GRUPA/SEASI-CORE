"""SDK tests: module builder, handshake and end-to-end execution."""

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
from seasi_core.kernel.module_registry import ModuleRegistry
from seasi_core.kernel.registry import ActionRegistry, WorkflowRegistry
from seasi_core.orchestration.runner import NeutralRunner, WorkflowStatus
from seasi_core.sdk import (
    LoadedModule,
    ModuleBuilder,
    ModuleError,
    install_module,
)

TENANT = TenantScope(tenant_id="acme", case_ref="c-1")


def _read(cid: str) -> CapabilitySpec:
    return CapabilitySpec(capability_id=cid, version="1.0.0", effect=EffectClass.READ)


def _draft(cid: str) -> CapabilitySpec:
    return CapabilitySpec(capability_id=cid, version="1.0.0", effect=EffectClass.LOCAL_DRAFT)


def _gated(cid: str) -> CapabilitySpec:
    return CapabilitySpec(
        capability_id=cid,
        version="1.0.0",
        effect=EffectClass.EXTERNAL_MUTATION,
        approval=ApprovalPolicy.REQUIRED,
        idempotent=True,
    )


def _wf(workflow_id: str, cap: str, *, gated: bool = False) -> WorkflowDefinition:
    mid = "review" if gated else "reviewed"
    states = (
        StateSpec(name="start"),
        StateSpec(name=mid),
        StateSpec(name="done", terminal=True),
    )
    transitions = (
        TransitionSpec(from_state="start", to_state=mid),
        TransitionSpec(
            from_state=mid,
            to_state="done",
            action=ActionCall(capability_id=cap, input={"k": "v"}),
        ),
    )
    return WorkflowDefinition(
        workflow_id=workflow_id,
        revision=1,
        initial_state="start",
        states=states,
        transitions=transitions,
    )


def _sample_module() -> LoadedModule:
    return (
        ModuleBuilder("demo-module", "0.1.0", "demo")
        .capability(_read("demo.read"))
        .capability(_draft("demo.draft"))
        .capability(_gated("demo.dispatch"))
        .workflow(_wf("demo.simple", "demo.draft"))
        .workflow(_wf("demo.gated", "demo.dispatch", gated=True))
        .handler("demo.read", lambda t, c, p: {"read": True})
        .handler("demo.draft", lambda t, c, p: {"drafted": True})
        .handler("demo.dispatch", lambda t, c, p: {"dispatched": True})
        .build()
    )


class TestBuilder:
    def test_manifest_autofilled_and_sorted(self) -> None:
        module = _sample_module()
        assert module.manifest.capabilities == (
            "demo.dispatch",
            "demo.draft",
            "demo.read",
        )
        assert module.manifest.workflows == ("demo.gated", "demo.simple")

    def test_duplicate_capability_rejected(self) -> None:
        with pytest.raises(ModuleError, match="duplicate capability"):
            ModuleBuilder("demo", "0.1.0").capability(_read("demo.read")).capability(
                _read("demo.read")
            ).build()

    def test_handler_for_undeclared_capability(self) -> None:
        with pytest.raises(ModuleError, match="undeclared"):
            ModuleBuilder("demo", "0.1.0").handler("ghost.read", lambda t, c, p: {}).build()

    def test_workflow_with_foreign_capability(self) -> None:
        with pytest.raises(ModuleError, match="not owned"):
            ModuleBuilder("demo", "0.1.0").capability(_read("demo.read")).workflow(
                _wf("demo.x", "other.write")
            ).build()


class TestInstall:
    def test_install_registers_everything(self) -> None:
        actions, modules, workflows = (ActionRegistry(), ModuleRegistry(), WorkflowRegistry())
        install_module(
            _sample_module(),
            actions=actions,
            modules=modules,
            workflows=workflows,
        )
        assert len(actions) == 3 and len(modules) == 1 and len(workflows) == 2
        assert workflows.checksum("demo.simple") == workflows.get("demo.simple").checksum()

    def test_duplicate_install_rejected(self) -> None:
        actions, modules, workflows = (ActionRegistry(), ModuleRegistry(), WorkflowRegistry())
        module = _sample_module()
        install_module(module, actions=actions, modules=modules, workflows=workflows)
        with pytest.raises(Exception, match="duplicate"):
            install_module(module, actions=actions, modules=modules, workflows=workflows)


class TestEndToEnd:
    def test_module_workflow_runs_with_hitl_gate(self) -> None:
        actions, modules, workflows = (ActionRegistry(), ModuleRegistry(), WorkflowRegistry())
        module = _sample_module()
        install_module(module, actions=actions, modules=modules, workflows=workflows)

        runner = NeutralRunner(actions, handlers=dict(module.handlers))
        instance = runner.start(workflows.get("demo.gated"), TENANT)
        instance = runner.run(instance)
        assert instance.status is WorkflowStatus.PAUSED_APPROVAL

        intent = instance.pending_intent
        assert intent is not None and intent.capability_id == "demo.dispatch"

        instance = runner.run(
            instance,
            approver=lambda i: ApprovalDecision(
                intent_id=i.intent_id,
                approved=True,
                decided_by="reviewer",
                decided_at=utc_now(),
            ),
        )
        assert instance.status is WorkflowStatus.COMPLETED
        assert instance.data == {"dispatched": True}

    def test_simple_workflow_completes_inline(self) -> None:
        actions, modules, workflows = (ActionRegistry(), ModuleRegistry(), WorkflowRegistry())
        module = _sample_module()
        install_module(module, actions=actions, modules=modules, workflows=workflows)

        runner = NeutralRunner(actions, handlers=dict(module.handlers))
        instance = runner.start(workflows.get("demo.simple"), TENANT)
        instance = runner.run(instance)
        assert instance.status is WorkflowStatus.COMPLETED
        assert instance.data == {"drafted": True}


def test_handler_signature_compatibility() -> None:
    """Module handlers plug straight into the runner's handler protocol."""
    captured: dict[str, Any] = {}

    def handler(tenant, capability_id, payload):
        captured["tenant"] = tenant
        captured["cap"] = capability_id
        return {"ok": True}

    module = (
        ModuleBuilder("sig", "0.1.0")
        .capability(_read("sig.read"))
        .workflow(_wf("sig.simple", "sig.read"))
        .handler("sig.read", handler)
        .build()
    )
    actions, mds, wfs = ActionRegistry(), ModuleRegistry(), WorkflowRegistry()
    install_module(module, actions=actions, modules=mds, workflows=wfs)
    runner = NeutralRunner(actions, handlers=dict(module.handlers))
    instance = runner.start(wfs.get("sig.simple"), TENANT)
    runner.run(instance)
    assert captured["cap"] == "sig.read"
    assert captured["tenant"].tenant_id == "acme"
