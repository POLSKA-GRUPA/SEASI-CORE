"""Effect policy: which effect classes may run, and under what approval.

Defaults are fail-closed:
- ``READ`` allowed;
- ``LOCAL_DRAFT`` allowed;
- ``EXTERNAL_MUTATION`` allowed ONLY with a verified approval intent.

Policies are plain data: packs and deployments can tighten them (never
loosen beyond what ``CapabilitySpec`` already enforces).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from seasi_core.contracts.capabilities import EffectClass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class EffectPolicy:
    enabled: Mapping[EffectClass, bool] = field(
        default_factory=lambda: {
            EffectClass.READ: True,
            EffectClass.LOCAL_DRAFT: True,
            EffectClass.EXTERNAL_MUTATION: True,
        }
    )

    def allows(self, effect: EffectClass, *, approval_verified: bool) -> PolicyDecision:
        if not self.enabled.get(effect, False):
            return PolicyDecision(False, f"effect class disabled: {effect.value}")
        if effect is EffectClass.EXTERNAL_MUTATION and not approval_verified:
            return PolicyDecision(False, "external_mutation requires a verified approval intent")
        return PolicyDecision(True, "allowed")

    @classmethod
    def read_only(cls) -> EffectPolicy:
        """Strictest useful policy: only reads, no drafts, no mutations."""
        return cls(
            enabled={
                EffectClass.READ: True,
                EffectClass.LOCAL_DRAFT: False,
                EffectClass.EXTERNAL_MUTATION: False,
            }
        )
