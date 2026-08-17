"""HITL pause contract: a governed effect frozen until a human decides.

The pause is persisted as a ledger event (never only in RAM). Resolution
produces an ``ApprovalIntent`` sealed over the exact payload digest, reusing
the kernel's existing approval machinery (``contracts.evidence``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seasi_core.contracts.tenant import TenantScope

SCHEMA_VERSION = "seasi/hitl-pause/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HitlStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


Decision = Literal["approved", "rejected"]


class HitlPause(BaseModel):
    """A paused effect awaiting human decision; status changes are new events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pause_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default=SCHEMA_VERSION)
    session_id: UUID
    tenant: TenantScope
    capability_id: str = Field(min_length=1, max_length=128)
    payload_digest: str = Field(min_length=64, max_length=64)
    artifact_ref: UUID | None = None
    status: HitlStatus = HitlStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("payload_digest")
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        if not _SHA256_RE.match(value):
            raise ValueError("payload_digest must be a lowercase sha-256 hex digest")
        return value

    @model_validator(mode="after")
    def _expiry_and_decision_consistency(self) -> HitlPause:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be strictly after created_at")
        decided = self.decided_at is not None or self.decided_by is not None
        if self.status == HitlStatus.PENDING and decided:
            raise ValueError("pending pauses carry no decision fields")
        if self.status in (HitlStatus.APPROVED, HitlStatus.REJECTED):
            if self.decided_at is None or self.decided_by is None:
                raise ValueError("approved/rejected pauses require decided_at/decided_by")
            if self.decided_at < self.created_at:
                raise ValueError("decided_at must not precede created_at")
        if self.status == HitlStatus.EXPIRED and decided:
            raise ValueError("expired pauses carry no decision fields")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or _utc_now()) >= self.expires_at
