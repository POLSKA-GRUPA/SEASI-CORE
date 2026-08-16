"""SDK for product modules that plug into the SEASI kernel.

A *module* is the commercial unit of the platform: it declares a
``ModuleManifest``, owns a set of capabilities, ships workflows that only
use its own capabilities, and provides handlers (or adapter-backed
implementations) for them.

The handshake (``install_module``) is fail-closed:

- duplicate capability/module/workflow registration is rejected;
- a workflow may ONLY reference capabilities owned by the same module
  (cross-module composition is explicit, never implicit);
- the manifest must match exactly what the module actually ships;
- every manifest capability must exist in the action registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from seasi_core.contracts.capabilities import CapabilitySpec
from seasi_core.contracts.workflows import WorkflowDefinition
from seasi_core.kernel.module_registry import ModuleManifest, ModuleRegistry
from seasi_core.kernel.registry import ActionRegistry, WorkflowRegistry
from seasi_core.orchestration.runner import Handler


class ModuleError(ValueError):
    """Raised when a module violates the kernel handshake."""


@dataclass(frozen=True)
class LoadedModule:
    """A validated, ready-to-install module."""

    manifest: ModuleManifest
    capabilities: tuple[CapabilitySpec, ...]
    workflows: tuple[WorkflowDefinition, ...]
    handlers: Mapping[str, Handler]


class ModuleBuilder:
    """Fluent builder enforcing module invariants BEFORE install."""

    def __init__(self, module_id: str, version: str, description: str = "") -> None:
        self._manifest = ModuleManifest(
            module_id=module_id, version=version, description=description
        )
        self._capabilities: list[CapabilitySpec] = []
        self._workflows: list[WorkflowDefinition] = []
        self._handlers: dict[str, Handler] = {}

    def capability(self, spec: CapabilitySpec) -> Self:
        self._capabilities.append(spec)
        return self

    def workflow(self, definition: WorkflowDefinition) -> Self:
        self._workflows.append(definition)
        return self

    def handler(self, capability_id: str, handler: Handler) -> Self:
        self._handlers[capability_id] = handler
        return self

    def build(self) -> LoadedModule:
        cap_ids = [c.capability_id for c in self._capabilities]
        _reject_duplicates("capability", cap_ids)

        unknown_handlers = sorted(set(self._handlers) - set(cap_ids))
        if unknown_handlers:
            raise ModuleError(f"handlers attached to undeclared capabilities: {unknown_handlers}")

        wf_ids = [w.workflow_id for w in self._workflows]
        _reject_duplicates("workflow", wf_ids)

        owned = set(cap_ids)
        for workflow in self._workflows:
            foreign = sorted(workflow.referenced_capabilities() - owned)
            if foreign:
                raise ModuleError(
                    f"workflow {workflow.workflow_id!r} references capabilities "
                    f"not owned by module {self._manifest.module_id!r}: {foreign}"
                )

        manifest = self._manifest.model_copy(
            update={
                "capabilities": tuple(sorted(owned)),
                "workflows": tuple(sorted(set(wf_ids))),
            }
        )
        return LoadedModule(
            manifest=manifest,
            capabilities=tuple(self._capabilities),
            workflows=tuple(self._workflows),
            handlers=dict(self._handlers),
        )


def install_module(
    module: LoadedModule,
    *,
    actions: ActionRegistry,
    modules: ModuleRegistry,
    workflows: WorkflowRegistry,
) -> None:
    """Register a module into the kernel registries with full validation.

    Raises ``DuplicateRegistrationError``/``UnknownKeyError`` (registries)
    or ``ModuleError`` (handshake violations).
    """
    for spec in module.capabilities:
        actions.register(spec.capability_id, spec)
    for definition in module.workflows:
        definition.assert_capabilities_registered(actions)
        workflows.register(definition.workflow_id, definition)
    modules.register(module.manifest.module_id, module.manifest)

    modules.assert_consistent_with(actions)

    declared = set(module.manifest.workflows)
    shipped = {w.workflow_id for w in module.workflows}
    if declared != shipped:
        raise ModuleError(f"manifest workflows {sorted(declared)} != shipped {sorted(shipped)}")


def _reject_duplicates(kind: str, ids: list[str]) -> None:
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in ids:
        if item in seen:
            dupes.add(item)
        seen.add(item)
    if dupes:
        raise ModuleError(f"duplicate {kind} declarations: {sorted(dupes)}")
