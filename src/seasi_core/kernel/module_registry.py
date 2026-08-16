"""Module manifests: how external product modules declare themselves.

SEASI-CORE is a kernel; the product lines (autonomous-management,
accounting-and-payroll, marketing, ...) are SEPARATE private modules that
plug in by registering capabilities and workflows. A manifest is the
versioned handshake between a module and the kernel.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from seasi_core.kernel.registry import ActionRegistry, Registry

_MODULE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$")


class ModuleManifest(BaseModel):
    """Closed description of one pluggable module."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module_id: str = Field(min_length=2, max_length=64)
    version: str = Field(min_length=5, max_length=32)
    description: str = Field(default="", max_length=500)
    capabilities: tuple[str, ...] = ()
    workflows: tuple[str, ...] = ()
    requires_core: str = ">=0.1.0"

    @field_validator("module_id")
    @classmethod
    def _validate_module_id(cls, value: str) -> str:
        if not _MODULE_ID.match(value):
            raise ValueError(f"module_id must be kebab-case, got {value!r}")
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not _SEMVER.match(value):
            raise ValueError(f"version must be semver-like, got {value!r}")
        return value


class ModuleRegistry(Registry[ModuleManifest]):
    """Registry of module manifests."""

    def assert_consistent_with(self, actions: ActionRegistry) -> None:
        """Every manifest capability must exist in the action registry.

        Fail-closed handshake: a module that forgot to register a
        capability it declares is rejected at load time.
        """
        seen: set[str] = set()
        for module_id in sorted(self):
            manifest = self.get(module_id)
            for capability_id in manifest.capabilities:
                if capability_id in seen:
                    raise ValueError(f"capability {capability_id!r} declared by two modules")
                seen.add(capability_id)
                if capability_id not in actions:
                    raise ValueError(
                        f"module {module_id!r} declares unknown capability {capability_id!r}"
                    )
