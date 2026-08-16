"""Kernel public surface."""

from seasi_core.kernel.context import (
    TenantContextError,
    current_tenant,
    tenant_scope,
    try_current_tenant,
)
from seasi_core.kernel.effect_policy import EffectPolicy, PolicyDecision
from seasi_core.kernel.intent_binding import (
    IntentVerification,
    bind_intent,
    canonical_json,
    digest_bytes,
    digest_mapping,
    new_nonce,
    verify_intent,
)
from seasi_core.kernel.module_registry import ModuleManifest, ModuleRegistry
from seasi_core.kernel.registry import (
    ActionRegistry,
    DuplicateRegistrationError,
    RegistrationError,
    Registry,
    UnknownKeyError,
)

__all__ = [
    "ActionRegistry",
    "DuplicateRegistrationError",
    "EffectPolicy",
    "IntentVerification",
    "ModuleManifest",
    "ModuleRegistry",
    "PolicyDecision",
    "RegistrationError",
    "Registry",
    "TenantContextError",
    "UnknownKeyError",
    "bind_intent",
    "canonical_json",
    "current_tenant",
    "digest_bytes",
    "digest_mapping",
    "new_nonce",
    "tenant_scope",
    "try_current_tenant",
    "verify_intent",
]
