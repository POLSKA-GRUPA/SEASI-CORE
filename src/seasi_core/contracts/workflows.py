"""Workflow definition contract.

A workflow is a *versioned, immutable* state machine: states, transitions
and (optional) declarative action calls referencing registered capabilities.
The definition carries a deterministic checksum so every party can agree on
the exact graph being executed.

This contract is deliberately execution-agnostic: the neutral runner in
``orchestration`` executes it, and richer engines (graphs, DAGs) can be
adapted on top WITHOUT changing the contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seasi_core.contracts.capabilities import CapabilitySpec


class StateSpec(BaseModel):
    """One node of the workflow graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    terminal: bool = False
    description: str = Field(default="", max_length=500)


class ActionCall(BaseModel):
    """Declarative invocation of a registered capability.

    ``input`` carries static values. ``input_from`` maps input keys to
    dot-paths inside the accumulated workflow data, so a step can consume
    the output of previous steps declaratively. Bindings are resolved by
    the runner *before* an ``ApprovalIntent`` is sealed, so a human always
    approves the real resolved values; a missing path fails the workflow
    (fail-closed) instead of dispatching with partial input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str = Field(min_length=3, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)
    input_from: dict[str, str] = Field(default_factory=dict)


class TransitionSpec(BaseModel):
    """Edge of the graph; may declare the action it triggers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_state: str = Field(min_length=1, max_length=64)
    to_state: str = Field(min_length=1, max_length=64)
    action: ActionCall | None = None
    description: str = Field(default="", max_length=500)


class WorkflowDefinition(BaseModel):
    """Immutable, revisioned workflow with a deterministic checksum."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow_id: str = Field(min_length=3, max_length=128)
    revision: int = Field(ge=1)
    initial_state: str = Field(min_length=1, max_length=64)
    states: tuple[StateSpec, ...] = Field(min_length=1)
    transitions: tuple[TransitionSpec, ...] = Field(default=())

    @model_validator(mode="after")
    def _graph_is_consistent(self) -> WorkflowDefinition:
        names = [s.name for s in self.states]
        if len(set(names)) != len(names):
            raise ValueError("duplicate state names")
        if self.initial_state not in names:
            raise ValueError(f"initial_state {self.initial_state!r} is not a state")
        seen: set[tuple[str, str, str | None]] = set()
        for t in self.transitions:
            if t.from_state not in names:
                raise ValueError(f"transition from unknown state {t.from_state!r}")
            if t.to_state not in names:
                raise ValueError(f"transition to unknown state {t.to_state!r}")
            key = (t.from_state, t.to_state, t.action.capability_id if t.action else None)
            if key in seen:
                raise ValueError(f"duplicate transition {key}")
            seen.add(key)
        if not any(s.terminal for s in self.states):
            raise ValueError("workflow needs at least one terminal state")
        return self

    def state_is_terminal(self, name: str) -> bool:
        return any(s.name == name and s.terminal for s in self.states)

    def transitions_from(self, state: str) -> tuple[TransitionSpec, ...]:
        """Deterministic order: declaration order."""
        return tuple(t for t in self.transitions if t.from_state == state)

    def referenced_capabilities(self) -> frozenset[str]:
        return frozenset(t.action.capability_id for t in self.transitions if t.action is not None)

    def checksum(self) -> str:
        """SHA-256 over the canonical JSON of the definition."""
        from seasi_core.kernel.intent_binding import digest_mapping

        return digest_mapping(self.model_dump(mode="json"))

    def assert_capabilities_registered(self, registry: MembershipContainer) -> None:
        """Raise if any referenced capability is unknown to the registry.

        ``registry`` must support membership tests; ``Registry`` does.
        """
        missing = [c for c in sorted(self.referenced_capabilities()) if c not in registry]
        if missing:
            raise ValueError(f"workflow references unknown capabilities: {missing}")


from typing import Protocol, runtime_checkable  # noqa: E402


@runtime_checkable
class MembershipContainer(Protocol):
    """Minimal membership protocol used for registry checks."""

    def __contains__(self, key: object) -> bool: ...


def requires_effect(spec: CapabilitySpec) -> str:
    """Small helper used by runners to classify transitions."""
    return spec.effect.value
