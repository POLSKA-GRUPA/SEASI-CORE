"""Evidence and approval contracts.

``EvidenceRef`` points at the immutable origin of any data (document,
artifact or external system record) together with a content digest.

``ApprovalIntent`` is the sealed promise of a human: it binds an actor to
the SHA-256 digest of the exact payload that may be executed, with an
expiry. Approvals are granted for ONE intent and ONE digest; changing the
payload invalidates the approval.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seasi_core.contracts.tenant import TenantScope

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_APPROVAL_TTL_S = 900.0


class EvidenceRef(BaseModel):
    """Reference to the origin of a piece of data, with integrity digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["document", "artifact", "external"]
    uri: str = Field(min_length=1, max_length=2048)
    sha256: str | None = None
    external_system: str | None = Field(default=None, min_length=1, max_length=64)
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def _external_needs_system(self) -> EvidenceRef:
        if self.kind == "external" and not self.external_system:
            raise ValueError("kind='external' requires external_system")
        if self.kind != "external" and self.external_system:
            raise ValueError("external_system only allowed for kind='external'")
        return self

    @model_validator(mode="after")
    def _digest_shape(self) -> EvidenceRef:
        if self.sha256 is not None and not _SHA256.match(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-hex digest")
        return self


class ApprovalIntent(BaseModel):
    """Sealed human approval over an exact payload digest.

    Created by the kernel when a governed effect must run; verified via
    ``kernel.intent_binding.verify_intent`` before execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: UUID = Field(default_factory=uuid4)
    tenant: TenantScope
    actor: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    expires_at: datetime
    nonce: str = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def _expiry_after_creation(self) -> ApprovalIntent:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be strictly after created_at")
        return self

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class ApprovalDecision(BaseModel):
    """Human answer to an ``ApprovalIntent``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: UUID
    approved: bool
    decided_by: str = Field(min_length=1, max_length=128)
    decided_at: datetime
    note: str | None = Field(default=None, max_length=500)


def default_expiry(now: datetime, ttl_s: float = DEFAULT_APPROVAL_TTL_S) -> datetime:
    """Standard approval TTL (15 minutes by default)."""
    return now + timedelta(seconds=ttl_s)
