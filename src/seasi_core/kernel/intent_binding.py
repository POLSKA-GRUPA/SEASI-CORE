"""Canonical JSON digests and approval-intent verification.

Canonical JSON: UTF-8, sorted keys at every level, compact separators.
The digest binds tenant + capability + payload, so an approval is valid for
exactly ONE effect on exactly ONE payload for exactly ONE tenant.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from seasi_core.contracts.evidence import ApprovalIntent
from seasi_core.contracts.tenant import TenantScope


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Deterministic serialization used for all digests."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_mapping(payload: Mapping[str, Any]) -> str:
    return digest_bytes(canonical_json(payload))


def bind_intent(tenant: TenantScope, capability_id: str, payload: Mapping[str, Any]) -> str:
    """Digest of the exact governed effect that an approval will authorize."""
    binding = {
        "tenant_id": tenant.tenant_id,
        "case_ref": tenant.case_ref,
        "project_ref": tenant.project_ref,
        "capability_id": capability_id,
        "payload": dict(payload),
    }
    return digest_mapping(binding)


def new_nonce() -> str:
    """Opaque single-use nonce for approval intents."""
    return uuid4().hex + secrets.token_hex(4)


@dataclass(frozen=True)
class IntentVerification:
    ok: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.ok


def verify_intent(
    intent: ApprovalIntent,
    *,
    tenant: TenantScope,
    capability_id: str,
    payload: Mapping[str, Any],
    now: datetime,
) -> IntentVerification:
    """Verify an approval intent against the CURRENT execution attempt.

    Any mismatch (tenant, capability, payload digest, expiry, blank actor)
    invalidates the approval. Fail-closed: verification only passes when
    everything matches exactly.
    """
    reasons: list[str] = []

    if intent.tenant.tenant_id != tenant.tenant_id:
        reasons.append(
            f"tenant mismatch: intent={intent.tenant.tenant_id!r} execution={tenant.tenant_id!r}"
        )
    if intent.capability_id != capability_id:
        reasons.append(
            f"capability mismatch: intent={intent.capability_id!r} execution={capability_id!r}"
        )
    expected = bind_intent(tenant, capability_id, payload)
    if intent.payload_digest != expected:
        reasons.append("payload digest mismatch: approval does not cover this payload")
    if not intent.actor.strip():
        reasons.append("intent actor is blank")
    if intent.is_expired(now):
        reasons.append("intent expired")

    return IntentVerification(ok=not reasons, reasons=tuple(reasons))
