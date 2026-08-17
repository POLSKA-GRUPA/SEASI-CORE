"""The v0 RPC method surface (mirrors ShellApiManifest, single source)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from seasi_core.contracts.session import AgentSession
from seasi_core.contracts.shell_api import ShellErrorCode, build_manifest
from seasi_core.contracts.tenant import TenantScope
from seasi_core.harness import registered_names
from seasi_core.harness.registry import UnknownAdapter
from seasi_core.ledger.hitl import HitlError, HitlStore
from seasi_core.ledger.store import EventLedger
from seasi_core.rpc.server import Dispatcher, RpcError
from seasi_core.services.sessions import SessionError, SessionService


class SessionStartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    client_ref: str = Field(min_length=1, max_length=64)
    period_ref: str = Field(min_length=4, max_length=6)
    adapter: str = Field(default="pi", min_length=1, max_length=32)
    model_ref: str | None = Field(default=None, min_length=1, max_length=128)


class SessionRunParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=36, max_length=36)
    prompt: str = Field(min_length=1, max_length=1_000_000)
    budget_turns: int | None = Field(default=None, ge=1, le=10_000)


class TenantParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=50, ge=1, le=500)


class HitlCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=36, max_length=36)
    capability_id: str = Field(min_length=1, max_length=128)
    payload_digest: str = Field(min_length=64, max_length=64)
    ttl_s: float = Field(default=900, gt=0, le=86_400)


class HitlDecideParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pause_id: str = Field(min_length=36, max_length=36)
    decision: str = Field(pattern=r"^(approved|rejected)$")
    actor: str = Field(min_length=1, max_length=128)


def _scope(tenant_id: str) -> TenantScope:
    try:
        return TenantScope(tenant_id=tenant_id)
    except Exception as exc:  # pydantic ValidationError
        raise RpcError(
            ShellErrorCode.SEASI_TENANT_SCOPE, "invalid tenant scope", data=str(exc)
        ) from exc


def _uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise RpcError(ShellErrorCode.INVALID_PARAMS, f"{label} must be a UUID") from exc


def build_dispatcher(
    ledger: EventLedger,
    sessions: SessionService,
    hitl: HitlStore,
) -> Dispatcher:
    dispatcher = Dispatcher()

    def version(_params: dict[str, Any]) -> dict[str, Any]:
        import seasi_core

        return {
            "kernel_version": seasi_core.__version__ if hasattr(seasi_core, "__version__") else "0",
            "api": build_manifest().model_dump(mode="json"),
            "adapters": registered_names(),
        }

    def session_start(params: dict[str, Any]) -> dict[str, Any]:
        scope = _scope(params["tenant_id"])
        try:
            session = sessions.start(
                tenant=scope,
                client_ref=params["client_ref"],
                period_ref=params["period_ref"],
                adapter=params["adapter"],
                model_ref=params.get("model_ref"),
            )
        except (SessionError, UnknownAdapter) as exc:
            raise RpcError(
                ShellErrorCode.SEASI_UNKNOWN_ADAPTER, str(exc), data={"adapter": params["adapter"]}
            ) from exc
        return session.model_dump(mode="json")

    def session_run(params: dict[str, Any], notify: Any = None) -> dict[str, Any]:
        scope = _scope(params["tenant_id"])
        session_id = _uuid(params["session_id"], "session_id")
        session = _load_session(sessions, scope, session_id)
        budget = None
        if params.get("budget_turns"):
            from seasi_core.harness import HarnessBudget

            budget = HarnessBudget(max_turns=int(params["budget_turns"]))

        def on_event(event: object) -> None:
            if notify is None:
                return
            payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
            notify("seasi.session.event", {"session_id": str(session_id), "event": payload})

        events = sessions.run(session, params["prompt"], budget, on_event=on_event)
        return {
            "session_id": str(session_id),
            "events": [e.model_dump(mode="json") for e in events],
        }

    def event_tail(params: dict[str, Any]) -> dict[str, Any]:
        _scope(params["tenant_id"])
        records = ledger.tail(params["tenant_id"], int(params["limit"]))
        return {
            "events": [
                {
                    "seq": r.seq,
                    "event_id": str(r.event_id),
                    "event_type": r.event_type,
                    "occurred_at": r.occurred_at,
                    "payload": r.payload,
                    "hash": r.hash,
                }
                for r in records
            ]
        }

    def usage_summary(params: dict[str, Any]) -> dict[str, Any]:
        scope = _scope(params["tenant_id"])
        sessions_by_id: dict[str, dict[str, Any]] = {}
        for rec in ledger.events_of_type(scope.tenant_id, "session.created"):
            sid = str(rec.payload.get("session_id"))
            sessions_by_id[sid] = {
                "session_id": sid,
                "client_ref": rec.payload.get("client_ref"),
                "period_ref": rec.payload.get("period_ref"),
                "model": rec.payload.get("model_ref"),
                "turns": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        for rec in ledger.tail(scope.tenant_id, 1_000_000):
            payload = rec.payload
            sid = str(payload.get("session_id"))
            entry = sessions_by_id.get(sid)
            if entry is None:
                continue
            if rec.event_type in ("harness.message", "harness.tool_call"):
                entry["turns"] = int(entry["turns"]) + 1
            elif rec.event_type == "harness.usage":
                data = payload.get("data")
                if isinstance(data, dict):
                    entry["input_tokens"] += int(data.get("input_tokens") or 0)
                    entry["output_tokens"] += int(data.get("output_tokens") or 0)
        return {"sessions": list(sessions_by_id.values())}

    def hitl_create(params: dict[str, Any]) -> dict[str, Any]:
        from datetime import UTC, datetime

        from seasi_core.contracts.evidence import default_expiry
        from seasi_core.contracts.hitl import HitlPause

        scope = _scope(params["tenant_id"])
        session_id = _uuid(params["session_id"], "session_id")
        now = datetime.now(UTC)
        try:
            pause = HitlPause(
                session_id=session_id,
                tenant=scope,
                capability_id=params["capability_id"],
                payload_digest=params["payload_digest"],
                expires_at=default_expiry(now, ttl_s=float(params["ttl_s"])),
            )
        except ValidationError as exc:
            raise RpcError(
                ShellErrorCode.INVALID_PARAMS, "invalid hitl pause", data=str(exc)
            ) from exc
        created = hitl.create(pause)
        return created.model_dump(mode="json")

    def hitl_list(params: dict[str, Any]) -> dict[str, Any]:
        scope = _scope(params["tenant_id"])
        return {
            "pending": [p.model_dump(mode="json") for p in hitl.list_pending(scope)]
        }

    def hitl_decide(params: dict[str, Any]) -> dict[str, Any]:
        pause_id = _uuid(params["pause_id"], "pause_id")
        try:
            intent = hitl.decide(
                pause_id, "approved" if params["decision"] == "approved" else "rejected",
                params["actor"],
            )
        except HitlError as exc:
            raise RpcError(
                ShellErrorCode.SEASI_FAIL_CLOSED, str(exc), data={"pause_id": str(pause_id)}
            ) from exc
        return {"intent": intent.model_dump(mode="json")}

    dispatcher.register("seasi.version", version)
    dispatcher.register("seasi.session.start", session_start, SessionStartParams)
    dispatcher.register("seasi.session.run", session_run, SessionRunParams)
    dispatcher.register("seasi.event.tail", event_tail, TenantParams)
    dispatcher.register("seasi.usage.summary", usage_summary, TenantParams)
    dispatcher.register("seasi.hitl.list", hitl_list, TenantParams)
    dispatcher.register("seasi.hitl.create", hitl_create, HitlCreateParams)
    dispatcher.register("seasi.hitl.decide", hitl_decide, HitlDecideParams)
    return dispatcher


def _load_session(
    sessions: SessionService, scope: TenantScope, session_id: UUID
) -> AgentSession:
    records = sessions.ledger.events_of_type(scope.tenant_id, "session.created")
    wanted = str(session_id)
    for record in reversed(records):
        if str(record.payload.get("session_id")) != wanted:
            continue
        try:
            return AgentSession.model_validate(record.payload)
        except Exception as exc:
            raise RpcError(
                ShellErrorCode.SEASI_FAIL_CLOSED,
                "stored session payload is invalid (ledger tampering?)",
                data={"session_id": wanted},
            ) from exc
    raise RpcError(
        ShellErrorCode.INVALID_PARAMS,
        f"session {session_id} not found for tenant {scope.tenant_id}",
    )
