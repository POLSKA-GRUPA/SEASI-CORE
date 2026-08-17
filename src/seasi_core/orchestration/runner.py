"""Neutral runner: deterministic execution with approval gates.

Execution model (v0.1):

- ``start`` creates a ``WorkflowInstance`` bound to an explicit tenant;
- ``run`` walks transitions in declaration order (deterministic);
- transitions without actions just move state;
- transitions with actions resolve the capability spec from the
  ``ActionRegistry``:
    * ``READ``/``LOCAL_DRAFT`` execute inline (optional handler);
    * ``EXTERNAL_MUTATION`` pauses the instance and creates a sealed
      ``ApprovalIntent`` over the exact payload digest. Execution resumes
      only when a human decision verifies (tenant, capability, payload,
      expiry) via ``kernel.intent_binding.verify_intent``;
- every step emits a typed ``EventEnvelope`` to the sink;
- step budget protects against runaway loops.

The runner NEVER talks to the network; handlers and effects belong to
modules behind ports.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from seasi_core.contracts.capabilities import CapabilitySpec, EffectClass
from seasi_core.contracts.events import EventEnvelope, build_event, utc_now
from seasi_core.contracts.evidence import ApprovalDecision, ApprovalIntent, default_expiry
from seasi_core.contracts.tenant import TenantScope
from seasi_core.contracts.workflows import ActionCall, TransitionSpec, WorkflowDefinition
from seasi_core.kernel.effect_policy import EffectPolicy
from seasi_core.kernel.intent_binding import bind_intent, new_nonce, verify_intent
from seasi_core.kernel.registry import ActionRegistry
from seasi_core.observability.structured import log_event

Handler = Callable[[TenantScope, str, Mapping[str, Any]], Mapping[str, Any]]
Approver = Callable[[ApprovalIntent], ApprovalDecision]


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RunFailure(Exception):
    status_detail: str


class WorkflowError(RuntimeError):
    """Raised on invalid runner usage (unknown capability, bad graph...)."""


@dataclass
class WorkflowInstance:
    definition: WorkflowDefinition
    tenant: TenantScope
    state: str
    status: WorkflowStatus = WorkflowStatus.RUNNING
    data: dict[str, Any] = field(default_factory=dict)
    steps: int = 0
    pending_intent: ApprovalIntent | None = None
    pending_transition: TransitionSpec | None = None
    failure_reason: str | None = None
    history: list[EventEnvelope] = field(default_factory=list)
    _executing: bool = field(default=False, repr=False, compare=False)


class EventSink:
    """Collects events; override ``emit`` to persist externally."""

    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def emit(self, event: EventEnvelope) -> None:
        self.events.append(event)


class NeutralRunner:
    """Deterministic, approval-aware executor of ``WorkflowDefinition``."""

    def __init__(
        self,
        capabilities: ActionRegistry,
        *,
        policy: EffectPolicy | None = None,
        sink: EventSink | None = None,
        handlers: Mapping[str, Handler] | None = None,
        max_steps: int = 10_000,
        approval_ttl_s: float = 900.0,
        now: Callable[[], datetime] = utc_now,
        logger_name: str = "seasi.runner",
    ) -> None:
        if max_steps < 1:
            raise WorkflowError("max_steps must be >= 1")
        self.capabilities = capabilities
        self.policy = policy or EffectPolicy()
        self.sink = sink or EventSink()
        self.handlers = dict(handlers) if handlers else {}
        self.max_steps = max_steps
        self.approval_ttl_s = approval_ttl_s
        self._now = now
        self._logger_name = logger_name

    # -- lifecycle -----------------------------------------------------------

    def start(
        self,
        definition: WorkflowDefinition,
        tenant: TenantScope,
        data: Mapping[str, Any] | None = None,
    ) -> WorkflowInstance:
        definition.assert_capabilities_registered(self.capabilities)
        instance = WorkflowInstance(
            definition=definition,
            tenant=tenant,
            state=definition.initial_state,
            data=dict(data or {}),
        )
        self._emit(
            instance,
            "workflow.started",
            {
                "workflow_id": definition.workflow_id,
                "revision": definition.revision,
                "checksum": definition.checksum(),
                "state": instance.state,
            },
        )
        return instance

    def run(
        self,
        instance: WorkflowInstance,
        approver: Approver | None = None,
    ) -> WorkflowInstance:
        """Advance until terminal, pause or failure. Idempotent on final states.

        HITL cadence: each call resolves AT MOST ONE pending approval. When
        ``approver`` is provided, the current pending intent is verified and
        resolved; execution then continues until the NEXT approval request
        (or a terminal state) and pauses again. A single call therefore
        represents exactly one human decision cycle — callers always get
        the instance back at a reviewable point.
        """
        if instance.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            return instance

        if instance._executing:
            raise WorkflowError(
                "run() is not reentrant: another run is active on this instance. "
                "The kernel is single-threaded per instance by contract; guard "
                "concurrent callers in the host application."
            )
        instance._executing = True
        try:
            return self._run_locked(instance, approver)
        finally:
            instance._executing = False

    def _run_locked(
        self,
        instance: WorkflowInstance,
        approver: Approver | None,
    ) -> WorkflowInstance:
        """Single-threaded core of run(); see run() for the contract."""

        resolved_here = False
        while instance.status not in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            if instance.status is WorkflowStatus.PAUSED_APPROVAL:
                if approver is None:
                    return instance
                if resolved_here:
                    # one human decision per call: stop at the next gate
                    return instance
                resumed = self._resolve_pending(instance, approver)
                if resumed is not WorkflowStatus.RUNNING:
                    return instance
                resolved_here = True
                continue

            transitions = instance.definition.transitions_from(instance.state)
            if not transitions:
                if instance.definition.state_is_terminal(instance.state):
                    instance.status = WorkflowStatus.COMPLETED
                    self._emit(instance, "workflow.completed", {"state": instance.state})
                    return instance
                self._fail(instance, f"no transition from non-terminal {instance.state!r}")
                return instance

            transition = transitions[0]
            try:
                self._advance(instance, transition)
            except WorkflowError as exc:  # explicit protocol violation
                self._fail(instance, str(exc))
                return instance

            instance.steps += 1
            if instance.steps >= self.max_steps:
                self._fail(instance, "step budget exhausted")
                return instance

        return instance

    # -- internals -----------------------------------------------------------

    def _advance(self, instance: WorkflowInstance, transition: TransitionSpec) -> None:
        action = transition.action
        if action is not None:
            spec = self.capabilities.get(action.capability_id)

            if spec.effect is EffectClass.EXTERNAL_MUTATION and (
                instance.pending_transition is None
            ):
                # First arrival at a governed effect: seal the intent and
                # pause. Effect policy is evaluated on resume, with the
                # verified approval present.
                payload = self._governed_payload(instance, transition)
                intent = ApprovalIntent(
                    tenant=instance.tenant,
                    actor="pending-human",
                    capability_id=action.capability_id,
                    payload_digest=bind_intent(instance.tenant, action.capability_id, payload),
                    created_at=self._now(),
                    expires_at=default_expiry(self._now(), self.approval_ttl_s),
                    nonce=new_nonce(),
                )
                instance.pending_intent = intent
                instance.pending_transition = transition
                instance.status = WorkflowStatus.PAUSED_APPROVAL
                self._emit(
                    instance,
                    "approval.requested",
                    {
                        "intent_id": str(intent.intent_id),
                        "capability_id": action.capability_id,
                        "state": instance.state,
                    },
                )
                log_event(
                    self._logger_name,
                    "approval.requested",
                    tenant_id=instance.tenant.tenant_id,
                    workflow_id=instance.definition.workflow_id,
                    case_id=instance.tenant.case_ref,
                    state=instance.state,
                    capability=action.capability_id,
                )
                return

            self._assert_effect(instance, spec, transition)
            approval_digest = (
                instance.pending_intent.payload_digest
                if instance.pending_intent is not None
                else None
            )

            action_input = self._resolved_input(instance, action)
            result = self._invoke_handler(instance, action.capability_id, action_input)
            if result:
                instance.data.update(result)
            self._emit(
                instance,
                "action.dispatched",
                {
                    "capability_id": action.capability_id,
                    "effect": spec.effect.value,
                    "from_state": transition.from_state,
                    "to_state": transition.to_state,
                    "approval_digest": approval_digest,
                    "input_digest": bind_intent(
                        instance.tenant, action.capability_id, {"input": action_input}
                    ),
                },
            )
            instance.pending_intent = None
            instance.pending_transition = None

        instance.state = transition.to_state
        self._emit(
            instance,
            "transition.applied",
            {"from": transition.from_state, "to": transition.to_state},
        )
        log_event(
            self._logger_name,
            "transition.applied",
            tenant_id=instance.tenant.tenant_id,
            workflow_id=instance.definition.workflow_id,
            case_id=instance.tenant.case_ref,
            state=instance.state,
        )

    def _resolve_pending(
        self, instance: WorkflowInstance, approver: Approver | None
    ) -> WorkflowStatus:
        intent = instance.pending_intent
        transition = instance.pending_transition
        if intent is None or transition is None or transition.action is None:
            self._fail(instance, "paused instance without pending effect")
            return instance.status

        if approver is None:
            return instance.status  # stay paused (caller has no human yet)

        decision = approver(intent)
        now = self._now()
        if decision.intent_id != intent.intent_id:
            self._emit(instance, "approval.mismatch", {"intent_id": str(decision.intent_id)})
            return instance.status

        payload = self._governed_payload(instance, transition)
        verification = verify_intent(
            _relabeled_intent(intent, decision),
            tenant=instance.tenant,
            capability_id=transition.action.capability_id,
            payload=payload,
            now=now,
        )
        if not decision.approved:
            self._emit(
                instance,
                "approval.rejected",
                {"intent_id": str(intent.intent_id), "decided_by": decision.decided_by},
            )
            instance.pending_intent = None
            instance.pending_transition = None
            self._fail(instance, f"approval rejected by {decision.decided_by!r}")
            return instance.status

        if not verification.ok:
            self._emit(
                instance,
                "approval.invalid",
                {"intent_id": str(intent.intent_id), "reasons": list(verification.reasons)},
            )
            return instance.status  # remain paused; invalid approval never executes

        self._emit(
            instance,
            "approval.granted",
            {"intent_id": str(intent.intent_id), "decided_by": decision.decided_by},
        )
        instance.status = WorkflowStatus.RUNNING
        return instance.status

    def _governed_payload(
        self, instance: WorkflowInstance, transition: TransitionSpec
    ) -> dict[str, Any]:
        assert transition.action is not None
        return {
            "workflow_id": instance.definition.workflow_id,
            "revision": instance.definition.revision,
            "from_state": transition.from_state,
            "to_state": transition.to_state,
            "input": self._resolved_input(instance, transition.action),
        }

    def _resolved_input(self, instance: WorkflowInstance, action: ActionCall) -> dict[str, Any]:
        """Merge static ``input`` with ``input_from`` bindings over workflow data.

        Resolution is fail-closed: a binding path that is not present in the
        accumulated data raises ``WorkflowError`` instead of dispatching the
        capability with partial input. Because governed payloads are built
        from the *resolved* input, the sealed digest covers the real values a
        human approves — mutating the underlying data after sealing breaks
        verification exactly like tampering with a static payload.
        """
        resolved = dict(action.input)
        for key, path in action.input_from.items():
            value: Any = instance.data
            for part in path.split("."):
                if not isinstance(value, Mapping) or part not in value:
                    raise WorkflowError(
                        f"input_from binding {path!r} for {key!r} not present in workflow data"
                    )
                value = value[part]
            resolved[key] = value
        return resolved

    def _invoke_handler(
        self, instance: WorkflowInstance, capability_id: str, action_input: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        handler = self.handlers.get(capability_id)
        if handler is None:
            return {}
        return handler(instance.tenant, capability_id, action_input)

    def _assert_effect(
        self, instance: WorkflowInstance, spec: CapabilitySpec, transition: TransitionSpec
    ) -> None:
        approval_verified = instance.pending_transition is not None
        decision = self.policy.allows(spec.effect, approval_verified=approval_verified)
        if not decision.allowed:
            raise WorkflowError(
                f"policy denied {spec.capability_id!r} on {transition.from_state!r}: "
                f"{decision.reason}"
            )

    def _fail(self, instance: WorkflowInstance, reason: str) -> None:
        instance.status = WorkflowStatus.FAILED
        instance.failure_reason = reason
        instance.pending_intent = None
        instance.pending_transition = None
        self._emit(instance, "workflow.failed", {"reason": reason})

    def _emit(self, instance: WorkflowInstance, event_type: str, payload: dict[str, Any]) -> None:
        event = build_event(event_type, instance.tenant, payload)
        instance.history.append(event)
        self.sink.emit(event)


def _relabeled_intent(intent: ApprovalIntent, decision: ApprovalDecision) -> ApprovalIntent:
    """Attach the human actor to the sealed intent before verification."""
    return intent.model_copy(update={"actor": decision.decided_by})
