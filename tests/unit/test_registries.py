"""Unit tests: registries, effect policy, capability spec invariants."""

import pytest

from seasi_core.contracts.capabilities import (
    ApprovalPolicy,
    CapabilitySpec,
    EffectClass,
)
from seasi_core.kernel.effect_policy import EffectPolicy
from seasi_core.kernel.module_registry import ModuleManifest, ModuleRegistry
from seasi_core.kernel.registry import (
    ActionRegistry,
    DuplicateRegistrationError,
    Registry,
    UnknownKeyError,
)


def _read_cap(cid: str = "docs.read") -> CapabilitySpec:
    return CapabilitySpec(capability_id=cid, version="1.0.0", effect=EffectClass.READ)


def _mutation_cap(cid: str = "ledger.post") -> CapabilitySpec:
    return CapabilitySpec(
        capability_id=cid,
        version="1.0.0",
        effect=EffectClass.EXTERNAL_MUTATION,
        approval=ApprovalPolicy.REQUIRED,
        idempotent=True,
    )


class TestRegistry:
    def test_register_and_get(self) -> None:
        reg: Registry[str] = Registry()
        reg.register("a", "alpha")
        assert reg.get("a") == "alpha"
        assert "a" in reg and len(reg) == 1

    def test_duplicate_rejected(self) -> None:
        reg: Registry[str] = Registry()
        reg.register("a", "alpha")
        with pytest.raises(DuplicateRegistrationError):
            reg.register("a", "beta")

    def test_unknown_rejected(self) -> None:
        reg: Registry[str] = Registry()
        with pytest.raises(UnknownKeyError):
            reg.get("missing")

    def test_snapshot_is_immutable_view(self) -> None:
        reg: Registry[str] = Registry()
        reg.register("a", "alpha")
        snap = reg.snapshot()
        reg.register("b", "beta")
        assert "b" not in snap and "b" in reg


class TestCapabilitySpec:
    def test_mutation_requires_approval(self) -> None:
        with pytest.raises(ValueError):
            CapabilitySpec(
                capability_id="x.post", version="1.0.0", effect=EffectClass.EXTERNAL_MUTATION
            )

    def test_read_cannot_require_approval(self) -> None:
        with pytest.raises(ValueError):
            CapabilitySpec(
                capability_id="x.read",
                version="1.0.0",
                effect=EffectClass.READ,
                approval=ApprovalPolicy.REQUIRED,
            )

    def test_id_must_be_namespaced(self) -> None:
        with pytest.raises(ValueError):
            CapabilitySpec(capability_id="nope", version="1.0.0", effect=EffectClass.READ)


class TestEffectPolicy:
    def test_default_denies_mutation_without_approval(self) -> None:
        policy = EffectPolicy()
        ok = policy.allows(EffectClass.READ, approval_verified=False)
        assert ok.allowed
        denied = policy.allows(EffectClass.EXTERNAL_MUTATION, approval_verified=False)
        assert not denied.allowed

    def test_mutation_allowed_with_verified_approval(self) -> None:
        policy = EffectPolicy()
        ok = policy.allows(EffectClass.EXTERNAL_MUTATION, approval_verified=True)
        assert ok.allowed

    def test_read_only_policy(self) -> None:
        policy = EffectPolicy.read_only()
        assert policy.allows(EffectClass.READ, approval_verified=False).allowed
        assert not policy.allows(EffectClass.LOCAL_DRAFT, approval_verified=False).allowed
        assert not policy.allows(EffectClass.EXTERNAL_MUTATION, approval_verified=True).allowed


class TestModuleRegistry:
    def test_manifest_and_consistency(self) -> None:
        actions = ActionRegistry()
        actions.register("docs.read", _read_cap())
        actions.register("ledger.post", _mutation_cap())

        modules = ModuleRegistry()
        modules.register(
            "docs",
            ModuleManifest(
                module_id="docs",
                version="0.1.0",
                capabilities=("docs.read",),
            ),
        )
        modules.assert_consistent_with(actions)

    def test_manifest_unknown_capability_fails(self) -> None:
        actions = ActionRegistry()
        actions.register("docs.read", _read_cap())
        modules = ModuleRegistry()
        modules.register(
            "bad",
            ModuleManifest(module_id="bad", version="0.1.0", capabilities=("ghost.read",)),
        )
        with pytest.raises(ValueError, match="unknown capability"):
            modules.assert_consistent_with(actions)

    def test_manifest_bad_id(self) -> None:
        with pytest.raises(ValueError):
            ModuleManifest(module_id="Bad Id", version="0.1.0")
