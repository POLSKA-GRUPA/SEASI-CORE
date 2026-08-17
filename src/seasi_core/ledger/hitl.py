"""Ledger-backed HITL queue: pauses persisted as events, decided by humans.

Stateless in RAM, stateful in SQLite: a pause is recreated by replaying
``hitl.pause.created`` events; every decision appends a new event carrying a
sealed ``ApprovalIntent`` over the exact payload digest. Nothing here can
block on in-memory ``input()``.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from seasi_core.contracts.events import build_event
from seasi_core.contracts.evidence import ApprovalIntent, default_expiry
from seasi_core.contracts.hitl import Decision, HitlPause, HitlStatus
from seasi_core.contracts.tenant import TenantScope
from seasi_core.ledger.store import EventLedger

PAUSE_CREATED = "hitl.pause.created"
PAUSE_DECIDED = "hitl.pause.decided"
PAUSE_EXPIRED = "hitl.pause.expired"


class HitlError(Exception):
    """Fail-closed HITL violations (unknown/expired/already-decided pause)."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HitlStore(BaseModel):
    """Persisted queue of governed pauses; state comes from the ledger."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ledger: EventLedger

    def create(self, pause: HitlPause) -> HitlPause:
        self.ledger.append(
            build_event(PAUSE_CREATED, pause.tenant, pause.model_dump(mode="json"))
        )
        return pause

    def list_pending(self, tenant: TenantScope) -> list[HitlPause]:
        pauses = {
            str(rec.payload["pause_id"]): _pause_from_payload(rec.payload)
            for rec in self.ledger.events_of_type(tenant.tenant_id, PAUSE_CREATED)
        }
        for rec in self.ledger.events_of_type(tenant.tenant_id, PAUSE_DECIDED):
            pauses.pop(str(rec.payload.get("pause_id")), None)
        for rec in self.ledger.events_of_type(tenant.tenant_id, PAUSE_EXPIRED):
            pauses.pop(str(rec.payload.get("pause_id")), None)
        pending = [p for p in pauses.values() if p.status == HitlStatus.PENDING]
        return sorted(pending, key=lambda p: p.created_at)

    def decide(self, pause_id: UUID, decision: Decision, actor: str) -> ApprovalIntent:
        pause = self._load_pause(pause_id)
        now = _utc_now()
        if pause.status != HitlStatus.PENDING:
            msg = f"pause {pause_id} is not pending (status={pause.status})"
            raise HitlError(msg)
        if pause.is_expired(now):
            self.ledger.append(
                build_event(PAUSE_EXPIRED, pause.tenant, {"pause_id": str(pause_id)})
            )
            msg = f"pause {pause_id} expired at {pause.expires_at.isoformat()}"
            raise HitlError(msg)

        intent = ApprovalIntent(
            tenant=pause.tenant,
            actor=actor,
            capability_id=pause.capability_id,
            payload_digest=pause.payload_digest,
            created_at=now,
            expires_at=default_expiry(now),
            nonce=secrets.token_urlsafe(16),
        )
        resolved = pause.model_copy(
            update={
                "status": HitlStatus(decision),
                "decided_at": now,
                "decided_by": actor,
            }
        )
        self.ledger.append(
            build_event(
                PAUSE_DECIDED,
                pause.tenant,
                {
                    "pause_id": str(pause_id),
                    "decision": decision,
                    "decided_by": actor,
                    "intent": intent.model_dump(mode="json"),
                    "resolved": resolved.model_dump(mode="json"),
                },
            )
        )
        return intent

    def _load_pause(self, pause_id: UUID) -> HitlPause:
        wanted = str(pause_id)
        latest: HitlPause | None = None
        for rec in self.ledger.events_of_type_all(PAUSE_CREATED):
            if str(rec.payload.get("pause_id")) == wanted:
                latest = _pause_from_payload(rec.payload)
        if latest is None:
            msg = f"unknown pause {pause_id}"
            raise HitlError(msg)
        for rec in self.ledger.events_of_type_all(PAUSE_DECIDED):
            if str(rec.payload.get("pause_id")) == wanted:
                resolved = rec.payload.get("resolved")
                if isinstance(resolved, dict):
                    return HitlPause.model_validate(resolved)
        return latest


def _pause_from_payload(payload: dict[str, object]) -> HitlPause:
    return HitlPause.model_validate(payload)
