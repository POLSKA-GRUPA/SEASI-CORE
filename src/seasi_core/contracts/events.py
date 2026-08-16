"""Event envelope: the only shape the kernel emits and persists.

Every event carries its tenant scope, timestamps, correlation/causation ids
and an explicit schema version. Payloads are digested (SHA-256 over the
canonical JSON) so downstream consumers can verify integrity.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from seasi_core.contracts.tenant import TenantScope

SCHEMA_VERSION = "seasi.event/v1"
_EVENT_TYPE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")


def utc_now() -> datetime:
    """Timezone-aware current UTC time (single source for the kernel)."""
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    """Immutable, versioned event record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default=SCHEMA_VERSION)
    event_type: str = Field(min_length=3, max_length=128)
    tenant: TenantScope
    occurred_at: datetime = Field(default_factory=utc_now)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    causation_id: str | None = Field(default=None, min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_digest: str | None = None

    def with_digest(self) -> EventEnvelope:
        """Return a copy with ``payload_digest`` computed over canonical JSON."""
        from seasi_core.kernel.intent_binding import digest_mapping

        return self.model_copy(update={"payload_digest": digest_mapping(self.payload)})


def build_event(
    event_type: str,
    tenant: TenantScope,
    payload: dict[str, Any] | None = None,
    *,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> EventEnvelope:
    """Factory used across the kernel; validates the event_type grammar."""
    if not _EVENT_TYPE.match(event_type):
        raise ValueError(f"event_type must be dot-namespaced, got {event_type!r}")
    return EventEnvelope(
        event_type=event_type,
        tenant=tenant,
        payload=payload or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
        occurred_at=occurred_at or utc_now(),
    ).with_digest()
