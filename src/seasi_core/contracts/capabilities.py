"""Capability contracts: the unit of governed effect in the kernel.

A *capability* is anything a module can do: read a client file, draft a
document, post an entry to an external ledger... Capabilities declare their
effect class up front, and the kernel enforces:

- ``READ`` and ``LOCAL_DRAFT`` effects may run without approval;
- ``EXTERNAL_MUTATION`` effects ALWAYS require a sealed approval intent
  bound to the exact payload digest (see ``kernel.intent_binding``).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CAPABILITY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(-[a-z0-9.-]+)?$")


class EffectClass(StrEnum):
    """Classification of the side effect a capability produces."""

    READ = "read"
    LOCAL_DRAFT = "local_draft"
    EXTERNAL_MUTATION = "external_mutation"


class ApprovalPolicy(StrEnum):
    """When an approval intent is required for a capability."""

    NEVER = "never"
    REQUIRED = "required"


class CapabilitySpec(BaseModel):
    """Closed, versioned description of one capability.

    ``approval`` is derived-consistent with ``effect``: external mutations
    must declare ``REQUIRED``; read/draft effects must declare ``NEVER``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str = Field(min_length=3, max_length=128)
    version: str = Field(min_length=5, max_length=32)
    effect: EffectClass
    description: str = Field(default="", max_length=500)
    input_schema_ref: str | None = None
    output_schema_ref: str | None = None
    timeout_s: float = Field(default=30.0, gt=0.0, le=3600.0)
    idempotent: bool = False
    approval: ApprovalPolicy = ApprovalPolicy.NEVER

    @field_validator("capability_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _CAPABILITY_ID.match(value):
            raise ValueError(
                "capability_id must be dot-namespaced lowercase "
                f"(e.g. 'fiscal.invoice.read'), got {value!r}"
            )
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        if not _VERSION.match(value):
            raise ValueError(f"version must be semver-like, got {value!r}")
        return value

    @model_validator(mode="after")
    def _effect_approval_consistency(self) -> CapabilitySpec:
        if self.effect is EffectClass.EXTERNAL_MUTATION:
            if self.approval is not ApprovalPolicy.REQUIRED:
                raise ValueError("external_mutation capabilities require approval")
        elif self.approval is not ApprovalPolicy.REQUIRED:
            pass
        else:
            raise ValueError("read/local_draft capabilities must not require approval")
        return self
