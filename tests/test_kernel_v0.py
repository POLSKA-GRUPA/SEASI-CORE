"""Kernel additions: scope guard, ledger chain, HITL store, harness, RPC."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from seasi_core.contracts.events import build_event
from seasi_core.contracts.hitl import HitlPause
from seasi_core.contracts.tenant import TenantScope
from seasi_core.harness.port import HarnessBudget, HarnessEventKind, SessionSpec
from seasi_core.harness.process import ProcessHarness
from seasi_core.harness.registry import UnknownAdapter, build, register, registered_names
from seasi_core.kernel.scope_guard import ScopeViolation, TenantPathGuard
from seasi_core.ledger.hitl import HitlError, HitlStore
from seasi_core.ledger.store import EventLedger
from seasi_core.rpc.methods import build_dispatcher
from seasi_core.rpc.server import serve


def _tenant(name: str = "demo") -> TenantScope:
    return TenantScope(tenant_id=name)


# -- scope guard --------------------------------------------------------------


def test_scope_guard_resolves_inside(tmp_path: Path) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="demo")
    resolved = guard.resolve("clientes/X/factura.pdf")
    assert str(resolved).startswith(str(tmp_path / "demo"))


@pytest.mark.parametrize("bad", ["/etc/passwd", "../other/file", "a/../../b", "~/x"])
def test_scope_guard_rejects_escapes(tmp_path: Path, bad: str) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="demo")
    with pytest.raises(ScopeViolation):
        guard.resolve(bad)


def test_scope_guard_ensure_absolute(tmp_path: Path) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="demo")
    guard.ensure(tmp_path / "demo" / "sessions" / "x")
    with pytest.raises(ScopeViolation):
        guard.ensure(tmp_path / "other" / "x")


# -- ledger chain -------------------------------------------------------------


def test_ledger_appends_and_verifies(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    for i in range(3):
        ledger.append(build_event("test.tick", _tenant(), {"i": i}))
    assert ledger.verify_chain("demo") is True
    records = ledger.tail("demo", limit=10)
    assert [r.payload["i"] for r in reversed(records)] == [0, 1, 2]


def test_ledger_detects_tampering(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    ledger.append(build_event("test.tick", _tenant(), {"i": 1}))
    with ledger._conn:  # deliberate tampering: rewrite a payload in place
        ledger._conn.execute(
            "UPDATE ledger_events SET payload_json = '{\"i\": 999}' WHERE seq = 1"
        )
    assert ledger.verify_chain("demo") is False


def test_ledger_isolates_tenants(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    ledger.append(build_event("test.tick", _tenant("demo"), {"i": 1}))
    ledger.append(build_event("test.tick", _tenant("other"), {"i": 2}))
    assert ledger.verify_chain("demo") is True
    assert ledger.verify_chain("other") is True
    assert len(ledger.tail("demo", 10)) == 1


# -- hitl store ---------------------------------------------------------------


def _digest(n: int = 64) -> str:
    return "b" * n


def _pause(**overrides: object) -> HitlPause:
    base: dict[str, object] = {
        "session_id": uuid4(),
        "tenant": _tenant(),
        "capability_id": "filing.submit",
        "payload_digest": _digest(),
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    base.update(overrides)
    return HitlPause.model_validate(base)


def test_hitl_create_decide_and_seal_intent(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    store = HitlStore(ledger=ledger)
    pause = store.create(_pause())
    assert store.list_pending(_tenant()) == [pause]

    intent = store.decide(pause.pause_id, "approved", "kenyi")
    assert intent.actor == "kenyi"
    assert intent.payload_digest == pause.payload_digest
    assert store.list_pending(_tenant()) == []
    assert ledger.verify_chain("demo") is True


def test_hitl_double_decide_fails_closed(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    store = HitlStore(ledger=ledger)
    pause = store.create(_pause())
    store.decide(pause.pause_id, "approved", "kenyi")
    with pytest.raises(HitlError):
        store.decide(pause.pause_id, "rejected", "otro")


def test_hitl_expired_pause_rejects_decision(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    store = HitlStore(ledger=ledger)
    now = datetime.now(UTC)
    pause = store.create(
        _pause(
            created_at=now - timedelta(minutes=60),
            expires_at=now - timedelta(seconds=1),
        )
    )
    with pytest.raises(HitlError):
        store.decide(pause.pause_id, "approved", "kenyi")


def test_hitl_unknown_pause(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    store = HitlStore(ledger=ledger)
    with pytest.raises(HitlError):
        store.decide(uuid4(), "approved", "kenyi")


# -- harness process ----------------------------------------------------------


def _fake_pi_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake-pi.py"
    script.write_text(
        "\n".join(
            [
                "import json, sys",
                "print(json.dumps({'type': 'message', 'text': 'hola'}))",
                "print(json.dumps({'type': 'tool_call', 'tool': 'read'}))",
                "print('raw line without json')",
            ]
        ),
        encoding="utf-8",
    )
    return script


def test_process_harness_streams_events(tmp_path: Path) -> None:
    script = _fake_pi_script(tmp_path)
    spec = SessionSpec(
        session_id=uuid4(),
        tenant=_tenant(),
        prompt="haz algo",
        cwd=tmp_path,
    )

    def argv(s: SessionSpec) -> list[str]:
        return [sys.executable, str(script)]

    harness = ProcessHarness("fake", argv)
    events = list(harness.start(spec))
    kinds = [e.kind for e in events]
    assert HarnessEventKind.SPAWNED in kinds
    assert kinds.count(HarnessEventKind.MESSAGE) == 2  # json + raw
    assert HarnessEventKind.TOOL_CALL in kinds
    assert kinds[-1] == HarnessEventKind.COMPLETED


def test_process_harness_budget_enforced(tmp_path: Path) -> None:
    script = tmp_path / "loop.py"
    script.write_text(
        "import time\nfor _ in range(50):\n    print('tick')\n    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    spec = SessionSpec(session_id=uuid4(), tenant=_tenant(), prompt="p", cwd=tmp_path)
    harness = ProcessHarness(
        "fake", lambda s: [sys.executable, str(script)]
    )
    events = list(harness.start(spec, HarnessBudget(deadline_s=0.2)))
    assert events[-1].kind == HarnessEventKind.FAILED
    assert events[-1].data["reason"] == "budget_exceeded"


def test_registry_fail_closed() -> None:
    register("fake", lambda: None)  # type: ignore[arg-type, return-value]
    assert "fake" in registered_names()
    with pytest.raises(UnknownAdapter):
        build("no-existe")
    assert build("pi").name == "pi"


# -- rpc server ---------------------------------------------------------------


class _IO:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.out: list[str] = []

    def __iter__(self) -> _IO:
        return self

    def __next__(self) -> str:
        if not self._lines:
            raise StopIteration
        return self._lines.pop(0)

    def write(self, data: str) -> None:
        self.out.append(data)

    def flush(self) -> None:
        return None


def test_rpc_happy_and_errors(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    from seasi_core.services.sessions import SessionService

    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)

    start_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "seasi.session.start",
        "params": {
            "tenant_id": "demo",
            "client_ref": "B00000091",
            "period_ref": "2026T3",
        },
    }
    io = _IO(
        [
            "no es json {{{",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "seasi.nope"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "seasi.session.start",
                    "params": {"tenant_id": "demo", "period_ref": "mal"},
                }
            ),
            json.dumps(start_req),
        ]
    )
    serve(io, io, dispatcher)
    responses = [json.loads(line) for line in io.out]
    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["error"]["code"] == -32601
    assert responses[2]["error"]["code"] == -32602
    session = responses[3]["result"]
    assert isinstance(session, dict)
    assert session["client_ref"] == "B00000091"
    assert session["state"] == "created"


def test_rpc_notification_no_response(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    from seasi_core.services.sessions import SessionService

    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)
    io = _IO(
        [
            json.dumps({"jsonrpc": "2.0", "method": "seasi.version"}),
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "seasi.version"}),
        ]
    )
    serve(io, io, dispatcher)
    assert len(io.out) == 1
    assert json.loads(io.out[0])["id"] == 9


def test_session_service_records_events(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    from seasi_core.services.sessions import SessionService

    def argv(s: SessionSpec) -> list[str]:
        script = tmp_path / "one.py"
        script.write_text(
            "import json\nprint(json.dumps({'type': 'message', 'text': 'ok'}))\n",
            encoding="utf-8",
        )
        return [sys.executable, str(script)]

    register("fake-run", lambda: ProcessHarness("fake-run", argv))
    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    session = sessions.start(_tenant(), "B00000091", "2026T3", adapter="fake-run")
    events = sessions.run(session, "prompt corto")
    kinds = [e.kind for e in events]
    assert kinds[-1] == HarnessEventKind.COMPLETED
    types = [r.event_type for r in ledger.tail("demo", 50)]
    assert "session.created" in types
    assert "session.state.running" in types
    assert "session.state.completed" in types
    assert "harness.message" in types
    assert ledger.verify_chain("demo") is True


def test_hitl_validation_error_surfaces(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        HitlPause(
            session_id=uuid4(),
            tenant=_tenant(),
            capability_id="filing.submit",
            payload_digest="corto",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
