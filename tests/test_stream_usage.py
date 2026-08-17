"""Streaming notifications + usage summary over the real RPC surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from seasi_core.contracts.tenant import TenantScope
from seasi_core.harness.port import HarnessEventKind, SessionSpec
from seasi_core.harness.process import ProcessHarness
from seasi_core.harness.registry import register
from seasi_core.ledger.hitl import HitlStore
from seasi_core.ledger.store import EventLedger
from seasi_core.rpc.methods import build_dispatcher
from seasi_core.rpc.server import serve
from seasi_core.services.sessions import SessionService


class _IO:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
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


def _adapter(tmp_path: Path, name: str, script_text: str) -> None:
    def argv(_spec: SessionSpec) -> list[str]:
        script = tmp_path / f"{name}.py"
        script.write_text(script_text, encoding="utf-8")
        return [sys.executable, str(script)]

    register(name, lambda: ProcessHarness(name, argv))


def test_session_run_streams_notifications_before_response(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)

    _adapter(
        tmp_path,
        "stream-fake",
        "import json\n"
        "print(json.dumps({'type': 'message', 'text': 'uno'}))\n"
        "print(json.dumps({'type': 'tool_call', 'tool': 'read'}))\n"
        "print(json.dumps({'type': 'message', 'text': 'dos'}))\n",
    )
    session = sessions.start(TenantScope(tenant_id="demo"), "B00000091", "2026T3",
                             adapter="stream-fake")

    io = _IO(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "seasi.session.run",
                    "params": {
                        "tenant_id": "demo",
                        "session_id": str(session.session_id),
                        "prompt": "p",
                    },
                }
            )
        ]
    )
    serve(io, io, dispatcher)

    lines = [json.loads(o) for o in io.out]
    notifications = [n for n in lines if "method" in n and "id" not in n]
    responses = [r for r in lines if "id" in r]
    assert len(responses) == 1 and responses[0]["id"] == 41

    kinds = [n["params"]["event"]["kind"] for n in notifications]
    # spawned → message → tool_call → message → completed, TODOS en vivo
    assert kinds[0] == "spawned"
    assert kinds.count("message") == 2
    assert "tool_call" in kinds
    assert kinds[-1] == "completed"

    # orden estricto: toda notificación llega ANTES de la respuesta
    assert io.out[-1].strip() == json.dumps(responses[0], ensure_ascii=False, default=str)

    # cada notificación referencia la sesión correcta
    for n in notifications:
        assert n["params"]["session_id"] == str(session.session_id)
        assert n["method"] == "seasi.session.event"


def test_usage_summary_aggregates_tokens_and_turns(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)

    _adapter(
        tmp_path,
        "usage-fake",
        "import json\n"
        "print(json.dumps({'type': 'message', 'text': 'hola'}))\n"
        "print(json.dumps({'type': 'usage', 'input_tokens': 120, 'output_tokens': 40}))\n"
        "print(json.dumps({'type': 'tool_call', 'tool': 'read'}))\n"
        "print(json.dumps({'type': 'usage', 'input_tokens': 30, 'output_tokens': 10}))\n",
    )
    session = sessions.start(TenantScope(tenant_id="demo"), "B00000092", "2026T3",
                             adapter="usage-fake", model_ref="groq/llama-3.3-70b-versatile")
    events = sessions.run(session, "p")
    assert events[-1].kind == HarnessEventKind.COMPLETED

    io = _IO(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "seasi.usage.summary",
                    "params": {"tenant_id": "demo"},
                }
            )
        ]
    )
    serve(io, io, dispatcher)
    result = json.loads(io.out[0])["result"]
    assert len(result["sessions"]) == 1
    row = result["sessions"][0]
    assert row["session_id"] == str(session.session_id)
    assert row["client_ref"] == "B00000092"
    assert row["model"] == "groq/llama-3.3-70b-versatile"
    assert row["turns"] == 2          # message + tool_call
    assert row["input_tokens"] == 150  # 120 + 30
    assert row["output_tokens"] == 50  # 40 + 10


def test_usage_summary_isolated_per_tenant(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)

    _adapter(tmp_path, "u2", "print('')\n")
    a = sessions.start(TenantScope(tenant_id="demo"), "A", "2026T3", adapter="u2")
    sessions.start(TenantScope(tenant_id="rival"), "B", "2026T3", adapter="u2")
    sessions.run(a, "p")

    io = _IO(
        [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "seasi.usage.summary",
                     "params": {"tenant_id": "demo"}})]
    )
    serve(io, io, dispatcher)
    result = json.loads(io.out[0])["result"]
    assert [s["client_ref"] for s in result["sessions"]] == ["A"]
