"""Append-only evidence ledger backed by SQLite.

Every agent action, harness event and HITL decision becomes an immutable
``EventEnvelope`` row with a SHA-256 hash chained to its predecessor.
Chains are per-tenant; verification recomputes the whole chain. The ledger
is the checkpoint substrate: state is rebuilt by replay, never by memory.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from seasi_core.contracts.events import EventEnvelope
from seasi_core.kernel.intent_binding import digest_mapping

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_events (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT    NOT NULL UNIQUE,
    tenant_id     TEXT    NOT NULL,
    event_type    TEXT    NOT NULL,
    occurred_at   TEXT    NOT NULL,
    payload_json  TEXT    NOT NULL,
    prev_hash     TEXT    NOT NULL,
    hash          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_tenant_seq
    ON ledger_events (tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_ledger_type
    ON ledger_events (tenant_id, event_type, seq);
"""


def _chain_hash(prev_hash: str, envelope: EventEnvelope, payload_digest: str) -> str:
    import hashlib

    material = f"{prev_hash}|{envelope.event_id}|{envelope.event_type}|{payload_digest}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerRecord:
    seq: int
    event_id: UUID
    tenant_id: str
    event_type: str
    occurred_at: str
    payload: dict[str, object]
    prev_hash: str
    hash: str


class EventLedger:
    """Thread-safe append-only store; one instance per database file."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    # -- append ---------------------------------------------------------------

    def append(self, envelope: EventEnvelope) -> LedgerRecord:
        payload_json = _dump_payload(envelope.payload)
        payload_digest = envelope.payload_digest or digest_mapping(envelope.payload)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT hash FROM ledger_events WHERE tenant_id = ? ORDER BY seq DESC LIMIT 1",
                (envelope.tenant.tenant_id,),
            ).fetchone()
            prev_hash = row["hash"] if row else "0" * 64
            event_hash = _chain_hash(prev_hash, envelope, payload_digest)
            cursor = self._conn.execute(
                "INSERT INTO ledger_events "
                "(event_id, tenant_id, event_type, occurred_at, payload_json, prev_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(envelope.event_id),
                    envelope.tenant.tenant_id,
                    envelope.event_type,
                    envelope.occurred_at.isoformat(),
                    payload_json,
                    prev_hash,
                    event_hash,
                ),
            )
            return LedgerRecord(
                seq=int(cursor.lastrowid or 0),
                event_id=envelope.event_id,
                tenant_id=envelope.tenant.tenant_id,
                event_type=envelope.event_type,
                occurred_at=envelope.occurred_at.isoformat(),
                payload=dict(envelope.payload),
                prev_hash=prev_hash,
                hash=event_hash,
            )

    # -- query ----------------------------------------------------------------

    def tail(self, tenant_id: str, limit: int = 50) -> list[LedgerRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger_events WHERE tenant_id = ? ORDER BY seq DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [_record(row) for row in rows]

    def events_of_type(self, tenant_id: str, event_type: str) -> list[LedgerRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger_events WHERE tenant_id = ? AND event_type = ? "
                "ORDER BY seq ASC",
                (tenant_id, event_type),
            ).fetchall()
        return [_record(row) for row in rows]

    def events_of_type_all(self, event_type: str) -> list[LedgerRecord]:
        """Tenant-agnostic lookup by event type (for globally unique ids)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger_events WHERE event_type = ? ORDER BY seq ASC",
                (event_type,),
            ).fetchall()
        return [_record(row) for row in rows]

    # -- verify ---------------------------------------------------------------

    def verify_chain(self, tenant_id: str) -> bool:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger_events WHERE tenant_id = ? ORDER BY seq ASC",
                (tenant_id,),
            ).fetchall()
        prev_hash = "0" * 64
        for row in rows:
            envelope_digest = digest_mapping(_load_payload(row["payload_json"]))
            expected = _chain_hash(
                prev_hash,
                _rebuild_envelope(row),
                envelope_digest,
            )
            if row["prev_hash"] != prev_hash or row["hash"] != expected:
                return False
            prev_hash = row["hash"]
        return True

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _dump_payload(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _load_payload(payload_json: str) -> dict[str, object]:
    import json

    loaded: object = json.loads(payload_json)
    if not isinstance(loaded, dict):
        msg = "ledger payload corrupted: not an object"
        raise ValueError(msg)
    return loaded


def _rebuild_envelope(row: sqlite3.Row) -> EventEnvelope:
    from seasi_core.contracts.tenant import TenantScope

    return EventEnvelope(
        event_id=UUID(row["event_id"]),
        tenant=TenantScope(tenant_id=row["tenant_id"]),
        event_type=row["event_type"],
        payload=_load_payload(row["payload_json"]),
    )


def _record(row: sqlite3.Row) -> LedgerRecord:
    return LedgerRecord(
        seq=int(row["seq"]),
        event_id=UUID(row["event_id"]),
        tenant_id=row["tenant_id"],
        event_type=row["event_type"],
        occurred_at=row["occurred_at"],
        payload=_load_payload(row["payload_json"]),
        prev_hash=row["prev_hash"],
        hash=row["hash"],
    )
