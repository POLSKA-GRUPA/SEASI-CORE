"""Unit tests: canonical digests and approval-intent verification."""

from datetime import timedelta

import pytest

from seasi_core.contracts.events import utc_now
from seasi_core.contracts.evidence import ApprovalIntent
from seasi_core.contracts.tenant import TenantScope
from seasi_core.kernel.intent_binding import (
    bind_intent,
    canonical_json,
    digest_mapping,
    new_nonce,
    verify_intent,
)


def _intent(
    tenant: TenantScope, capability: str, payload: dict, *, ttl_s: float = 900
) -> ApprovalIntent:
    now = utc_now()
    return ApprovalIntent(
        tenant=tenant,
        actor="human-1",
        capability_id=capability,
        payload_digest=bind_intent(tenant, capability, payload),
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_s),
        nonce=new_nonce(),
    )


class TestCanonicalJson:
    def test_key_order_is_irrelevant(self) -> None:
        a = {"a": 1, "b": {"x": 1, "y": 2}}
        b = {"b": {"y": 2, "x": 1}, "a": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_digest_stable(self) -> None:
        assert digest_mapping({"k": [1, 2]}) == digest_mapping({"k": [1, 2]})

    def test_payload_change_changes_digest(self) -> None:
        assert digest_mapping({"k": 1}) != digest_mapping({"k": 2})


class TestBindIntent:
    def test_binds_tenant(self) -> None:
        payload = {"x": 1}
        d1 = bind_intent(TenantScope(tenant_id="acme"), "cap.a", payload)
        d2 = bind_intent(TenantScope(tenant_id="beta"), "cap.a", payload)
        assert d1 != d2

    def test_binds_capability(self) -> None:
        t = TenantScope(tenant_id="acme")
        assert bind_intent(t, "cap.a", {}) != bind_intent(t, "cap.b", {})


class TestVerifyIntent:
    def test_valid_intent_passes(self) -> None:
        t = TenantScope(tenant_id="acme", case_ref="c1")
        payload = {"input": {"total": 225.50}}
        intent = _intent(t, "ledger.post", payload)
        result = verify_intent(
            intent,
            tenant=t,
            capability_id="ledger.post",
            payload=payload,
            now=utc_now(),
        )
        assert result.ok, result.reasons

    def test_tampered_payload_fails(self) -> None:
        t = TenantScope(tenant_id="acme")
        intent = _intent(t, "ledger.post", {"amount": 100})
        result = verify_intent(
            intent,
            tenant=t,
            capability_id="ledger.post",
            payload={"amount": 999},  # tampered after approval
            now=utc_now(),
        )
        assert not result.ok
        assert any("digest mismatch" in r for r in result.reasons)

    def test_expired_fails(self) -> None:
        t = TenantScope(tenant_id="acme")
        payload: dict = {}
        intent = _intent(t, "cap.x", payload)
        expired = intent.model_copy(
            update={
                "created_at": utc_now() - timedelta(seconds=2000),
                "expires_at": utc_now() - timedelta(seconds=1000),
            }
        )
        result = verify_intent(
            expired, tenant=t, capability_id="cap.x", payload=payload, now=utc_now()
        )
        assert not result.ok and any("expired" in r for r in result.reasons)

    def test_cross_tenant_fails(self) -> None:
        payload = {"x": 1}
        intent = _intent(TenantScope(tenant_id="acme"), "cap.x", payload)
        result = verify_intent(
            intent,
            tenant=TenantScope(tenant_id="beta"),  # different tenant executing
            capability_id="cap.x",
            payload=payload,
            now=utc_now(),
        )
        assert not result.ok and any("tenant mismatch" in r for r in result.reasons)

    def test_intent_expiry_validation(self) -> None:
        now = utc_now()
        with pytest.raises(ValueError):
            ApprovalIntent(
                tenant=TenantScope(tenant_id="acme"),
                actor="h",
                capability_id="cap.x",
                payload_digest="a" * 64,
                created_at=now,
                expires_at=now,  # must be strictly after
                nonce=new_nonce(),
            )
