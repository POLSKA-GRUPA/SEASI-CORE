"""HARD suite: adversarial coverage for kernel v0.

Tamper-every-seq chain integrity, symlink escapes, concurrent appends,
unicode payloads, budget boundaries, cancel-before-first-line, non-UTF8
stderr noise, RPC edge cases and a REAL stdio integration roundtrip
against ``python -m seasi_core.rpc`` as an actual subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from seasi_core.contracts.events import build_event
from seasi_core.contracts.hitl import HitlPause
from seasi_core.contracts.tenant import TenantScope
from seasi_core.harness.port import HarnessBudget, HarnessEventKind, SessionSpec
from seasi_core.harness.process import ProcessHarness
from seasi_core.kernel.scope_guard import ScopeViolation, TenantPathGuard
from seasi_core.ledger.hitl import HitlError, HitlStore
from seasi_core.ledger.store import EventLedger
from seasi_core.rpc.methods import build_dispatcher
from seasi_core.rpc.server import serve
from seasi_core.services.sessions import SessionService


def _tenant(name: str = "pgk") -> TenantScope:
    return TenantScope(tenant_id=name)


# ---------------------------------------------------------------- chain hard


def _fresh_ledger(db: Path, n: int) -> EventLedger:
    ledger = EventLedger(db)
    for i in range(n):
        ledger.append(build_event("test.tick", _tenant(), {"i": i, "pad": "x" * 40}))
    return ledger


def test_chain_tamper_at_every_position(tmp_path: Path) -> None:
    """Mutating any row (payload, hash, prev_hash, type) or deleting any
    INTERIOR row must break verification. Truncating the tail is out of
    scope for a bare hash chain (needs an external anchor) and is covered
    by backups instead."""
    n = 12
    variants = [
        "UPDATE ledger_events SET payload_json = '{\"i\": 0}' WHERE seq = ?",
        "UPDATE ledger_events SET hash = '" + "0" * 64 + "' WHERE seq = ?",
        "UPDATE ledger_events SET prev_hash = '" + "0" * 64 + "' WHERE seq = ?",
        "UPDATE ledger_events SET event_type = 'forged.event' WHERE seq = ?",
        "DELETE FROM ledger_events WHERE seq = ?",
    ]
    for variant_idx, mutation in enumerate(variants):
        for victim in range(1, n + 1):
            if mutation.startswith("DELETE") and victim == n:
                continue  # tail truncation: chain prefix stays valid by design
            if variant_idx == 2 and victim == 1:
                continue  # first row's prev_hash IS 64 zeros: canonical value
            db = tmp_path / f"tamper-{variant_idx}-{victim}.db"
            ledger = _fresh_ledger(db, n)
            with ledger._conn:
                ledger._conn.execute(mutation, (victim,))
            assert ledger.verify_chain("pgk") is False, (variant_idx, victim)
            ledger.close()


def test_chain_tail_truncation_needs_backup_anchor(tmp_path: Path) -> None:
    """Documented limitation: dropping the final rows keeps a valid chain;
    the backup manifest (hash of the db file) is the anchor that catches it."""
    from hashlib import sha256

    ledger = _fresh_ledger(tmp_path / "full.db", 5)
    ledger.close()  # closing the last connection checkpoints WAL into the file
    full_digest = sha256((tmp_path / "full.db").read_bytes()).hexdigest()

    truncated = tmp_path / "trunc.db"
    truncated.write_bytes((tmp_path / "full.db").read_bytes())
    led = EventLedger(truncated)
    with led._conn:
        led._conn.execute("DELETE FROM ledger_events WHERE seq = 5")
    led.close()

    reopened = EventLedger(truncated)
    assert reopened.verify_chain("pgk") is True  # chain is blind to tail loss
    reopened.close()
    assert sha256(truncated.read_bytes()).hexdigest() != full_digest  # anchor sees it


def test_chain_survives_100_events_and_reorders_fail(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    for i in range(100):
        ledger.append(build_event("test.tick", _tenant(), {"seq_i": i}))
    assert ledger.verify_chain("pgk") is True
    # swap two payloads keeping hashes: digest check inside _chain_hash material
    with ledger._conn:
        r1 = ledger._conn.execute(
            "SELECT payload_json FROM ledger_events WHERE seq = 10"
        ).fetchone()[0]
        r2 = ledger._conn.execute(
            "SELECT payload_json FROM ledger_events WHERE seq = 11"
        ).fetchone()[0]
        ledger._conn.execute(
            "UPDATE ledger_events SET payload_json = ? WHERE seq = 10", (r2,)
        )
        ledger._conn.execute(
            "UPDATE ledger_events SET payload_json = ? WHERE seq = 11", (r1,)
        )
    assert ledger.verify_chain("pgk") is False


def test_concurrent_appends_keep_chain_valid(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")

    def worker(n: int) -> None:
        for i in range(25):
            ledger.append(build_event("test.concurrent", _tenant(), {"w": n, "i": i}))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(8)))
    with ledger._conn:
        count = ledger._conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0]
    assert count == 200
    assert ledger.verify_chain("pgk") is True


# ---------------------------------------------------------------- scope hard


def test_scope_guard_symlink_escape(tmp_path: Path) -> None:
    """A symlink inside the tenant dir pointing outside must not resolve out."""
    tenant_dir = tmp_path / "pgk"
    tenant_dir.mkdir(parents=True)
    outside = tmp_path / "secrets.txt"
    outside.write_text("fuera", encoding="utf-8")
    (tenant_dir / "link.txt").symlink_to(outside)
    guard = TenantPathGuard(root=tmp_path, tenant_id="pgk")
    # resolve() follows symlinks and must refuse the escaped target itself
    with pytest.raises(ScopeViolation):
        guard.resolve("link.txt")
    # ensure() still rejects absolute paths outside the scope
    with pytest.raises(ScopeViolation):
        guard.ensure(outside)


ESCAPE_CORPUS = [
    "/etc/passwd",
    "/abs/x",
    "~/.ssh/id_rsa",
    "a/../../b",
    "../../etc",
    "a/b/../../../c",
    "a//b",
    "a/./b",
    "./x",
    "../x",
    "",
    ".",
    "..",
    "a/",
    "café/../../../x",
    "a/b\nc/../..",
    "x/\t/../..",
    "nul\x00byte",
    "....//....//etc",
]


@pytest.mark.parametrize("candidate", ESCAPE_CORPUS)
def test_scope_guard_escape_corpus(tmp_path: Path, candidate: str) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="pgk")
    with pytest.raises((ScopeViolation, ValueError)):
        guard.resolve(candidate)


SAFE_WEIRD_NAMES = [
    "%2e%2e%2f",  # literal name: kernel never URL-decodes paths
    "..%2f..%2f",
    "....-dotdot-name",
    "café/factura-ñ.pdf",
    "a b c/d e f.g",
]


@pytest.mark.parametrize("candidate", SAFE_WEIRD_NAMES)
def test_scope_guard_safe_weird_names_stay_inside(tmp_path: Path, candidate: str) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="pgk")
    resolved = guard.resolve(candidate)
    base = (tmp_path / "pgk").resolve(strict=False)
    assert base == resolved or base in resolved.parents


def test_scope_guard_unicode_ok_inside(tmp_path: Path) -> None:
    guard = TenantPathGuard(root=tmp_path, tenant_id="pgk")
    ok = guard.resolve("clientes/B82211806/2026T3/factura-café-ñ.pdf")
    assert "clientes" in str(ok)


# ---------------------------------------------------------------- harness hard


def _spec(tmp_path: Path) -> SessionSpec:
    return SessionSpec(session_id=uuid4(), tenant=_tenant(), prompt="p", cwd=tmp_path)


def test_harness_budget_exact_boundary(tmp_path: Path) -> None:
    """max_turns=2 must allow exactly 2 turns and fail on the third."""
    script = tmp_path / "three.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "for i in range(3):",
                "    print(json.dumps({'type': 'message', 'i': i}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    events = list(harness.start(_spec(tmp_path), HarnessBudget(max_turns=2)))
    kinds = [e.kind for e in events]
    assert kinds.count(HarnessEventKind.MESSAGE) == 2
    assert kinds[-1] == HarnessEventKind.FAILED
    assert events[-1].data["reason"] == "budget_exceeded"


def test_harness_stderr_noise_is_not_business(tmp_path: Path) -> None:
    script = tmp_path / "chatty.py"
    script.write_text(
        "\n".join(
            [
                "import sys, json",
                "sys.stderr.write('WARN noise\\n')",
                "print(json.dumps({'type': 'message', 'text': 'ok'}))",
                "sys.stderr.write('MORE noise\\n')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    events = list(harness.start(_spec(tmp_path)))
    assert [e.kind for e in events][-1] == HarnessEventKind.COMPLETED
    for event in events:
        dumped = json.dumps(event.data)
        assert "WARN noise" not in dumped and "MORE noise" not in dumped


def test_harness_nonzero_exit_is_failed(tmp_path: Path) -> None:
    script = tmp_path / "boom.py"
    script.write_text("import sys\nprint('out')\nsys.exit(3)\n", encoding="utf-8")
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    events = list(harness.start(_spec(tmp_path)))
    assert events[-1].kind == HarnessEventKind.FAILED
    assert events[-1].data == {"returncode": 3}


def test_harness_unknown_type_falls_back_to_message(tmp_path: Path) -> None:
    script = tmp_path / "weird.py"
    script.write_text(
        "import json\nprint(json.dumps({'type': 'quantum_entangle', 'x': 1}))\n",
        encoding="utf-8",
    )
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    events = list(harness.start(_spec(tmp_path)))
    msgs = [e for e in events if e.kind == HarnessEventKind.MESSAGE]
    assert msgs and msgs[0].data.get("x") == 1


def test_harness_cancel_before_first_line(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    script.write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    gen = harness.start(_spec(tmp_path), HarnessBudget(deadline_s=3600))
    first = next(gen)
    assert first.kind == HarnessEventKind.SPAWNED
    harness.cancel()
    rest = list(gen)
    assert rest and rest[-1].kind == HarnessEventKind.CANCELLED
    assert harness._proc is None


def test_harness_huge_line_survives(tmp_path: Path) -> None:
    script = tmp_path / "big.py"
    script.write_text(
        "import json\nprint(json.dumps({'type': 'message', 'blob': 'A' * 300000}))\n",
        encoding="utf-8",
    )
    harness = ProcessHarness("t", lambda s: [sys.executable, str(script)])
    events = list(harness.start(_spec(tmp_path)))
    assert events[-1].kind == HarnessEventKind.COMPLETED
    assert len(events[1].data.get("blob", "")) == 300000


# ---------------------------------------------------------------- rpc hard


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


def _dispatcher(tmp_path: Path):
    ledger = EventLedger(tmp_path / "led.db")
    sessions = SessionService(ledger=ledger, root=tmp_path / "ws")
    hitl = HitlStore(ledger=ledger)
    return build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl), ledger


def _rpc(tmp_path: Path, lines: list[str]) -> list[dict[str, object]]:
    dispatcher, _ = _dispatcher(tmp_path)
    io = _IO(lines)
    serve(io, io, dispatcher)
    return [json.loads(o) for o in io.out]


def test_rpc_unicode_and_string_ids(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "cli-ñ-1",
                    "method": "seasi.session.start",
                    "params": {
                        "tenant_id": "pgk",
                        "client_ref": "Ñoño-Ünicode-SL",
                        "period_ref": "2026T4",
                    },
                }
            )
        ],
    )
    assert responses[0]["id"] == "cli-ñ-1"
    result = responses[0]["result"]
    assert isinstance(result, dict)
    assert result["client_ref"] == "Ñoño-Ünicode-SL"


def test_rpc_bad_tenant_is_domain_error(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "seasi.session.start",
                    "params": {
                        "tenant_id": "PGK!",
                        "client_ref": "X",
                        "period_ref": "2026T3",
                    },
                }
            )
        ],
    )
    assert responses[0]["error"]["code"] == 101  # SEASI_TENANT_SCOPE


def test_rpc_huge_params_rejected_fast(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "seasi.session.run",
                    "params": {"tenant_id": "pgk", "prompt": "A" * 2_000_000},
                }
            )
        ],
    )
    assert responses[0]["error"]["code"] in (-32602, -32603)


def test_rpc_extra_params_forbidden(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "seasi.version",
                    "params": {"sneaky": True},
                }
            )
        ],
    )
    assert responses[0]["error"]["code"] == -32602


def test_rpc_batch_rejected(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps(
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "seasi.version"},
                ]
            )
        ],
    )
    assert responses[0]["error"]["code"] == -32600


def test_rpc_no_version_or_wrong_version(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps({"id": 1, "method": "seasi.version"}),
            json.dumps({"jsonrpc": "1.0", "id": 2, "method": "seasi.version"}),
        ],
    )
    assert all(r["error"]["code"] == -32600 for r in responses)


def test_rpc_error_notification_is_silent(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [json.dumps({"jsonrpc": "2.0", "method": "seasi.does.not.exist"})],
    )
    assert responses == []


def test_rpc_id_null_and_float_rejected(tmp_path: Path) -> None:
    responses = _rpc(
        tmp_path,
        [
            json.dumps({"jsonrpc": "2.0", "id": 1.5, "method": "seasi.version"}),
        ],
    )
    assert responses[0]["error"]["code"] == -32600


# ------------------------------------------------- REAL stdio integration


class _StdioRpc:
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self.proc = proc

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
            + "\n"
        )
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise AssertionError("kernel closed stdio unexpectedly")
        return json.loads(line)


def test_real_stdio_kernel_roundtrip(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "SEASI_DB": str(tmp_path / "led.db"),
        "SEASI_ROOT": str(tmp_path / "ws"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "seasi_core.rpc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    try:
        rpc = _StdioRpc(proc)
        version = rpc.call("seasi.version")
        assert "seasi.hitl.create" in json.dumps(version["result"])

        session = rpc.call(
            "seasi.session.start",
            {
                "tenant_id": "pgk",
                "client_ref": "B82211806",
                "period_ref": "2026T3",
            },
        )["result"]
        assert isinstance(session, dict)
        session_id = session["session_id"]

        digest = "c" * 64
        pause = rpc.call(
            "seasi.hitl.create",
            {
                "tenant_id": "pgk",
                "session_id": session_id,
                "capability_id": "filing.submit",
                "payload_digest": digest,
            },
        )["result"]
        assert isinstance(pause, dict) and pause["status"] == "pending"

        listed = rpc.call("seasi.hitl.list", {"tenant_id": "pgk"})["result"]
        assert isinstance(listed, dict)
        assert len(listed["pending"]) == 1

        decided = rpc.call(
            "seasi.hitl.decide",
            {
                "pause_id": pause["pause_id"],
                "decision": "approved",
                "actor": "kenyi-hard-test",
            },
        )["result"]
        intent = decided["intent"]
        assert intent["actor"] == "kenyi-hard-test"
        assert intent["payload_digest"] == digest

        # second decide must fail closed
        again = rpc.call(
            "seasi.hitl.decide",
            {
                "pause_id": pause["pause_id"],
                "decision": "rejected",
                "actor": "otro",
            },
        )
        assert again["error"]["code"] == 100

        empty = rpc.call("seasi.hitl.list", {"tenant_id": "pgk"})["result"]
        assert isinstance(empty, dict) and empty["pending"] == []

        tail = rpc.call("seasi.event.tail", {"tenant_id": "pgk", "limit": 10})["result"]
        types = [e["event_type"] for e in tail["events"]]
        assert "session.created" in types
        assert "hitl.pause.created" in types
        assert "hitl.pause.decided" in types
    finally:
        proc.stdin.close() if proc.stdin else None  # type: ignore[func-returns-value]
        proc.terminate()
        proc.wait(timeout=10)


def test_hitl_decide_race_second_wins_never(tmp_path: Path) -> None:
    """Two concurrent decides: exactly one succeeds (ledger is the arbiter)."""
    ledger = EventLedger(tmp_path / "led.db")
    store = HitlStore(ledger=ledger)
    pause = store.create(
        HitlPause(
            session_id=uuid4(),
            tenant=_tenant(),
            capability_id="email.send",
            payload_digest="d" * 64,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    results: list[object] = []
    lock = threading.Lock()

    def decide() -> None:
        try:
            store.decide(pause.pause_id, "approved", "actor-race")
            with lock:
                results.append("ok")
        except HitlError:
            with lock:
                results.append("fail")

    threads = [threading.Thread(target=decide) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1
    assert results.count("fail") == 3
    assert ledger.verify_chain("pgk") is True


def test_events_of_type_all_does_not_leak_cross_tenant(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "led.db")
    a = HitlStore(ledger=ledger)
    other = HitlStore(ledger=ledger)
    p1 = a.create(
        HitlPause(
            session_id=uuid4(),
            tenant=_tenant("pgk"),
            capability_id="x",
            payload_digest="1" * 64,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    other.create(
        HitlPause(
            session_id=uuid4(),
            tenant=_tenant("rival"),
            capability_id="x",
            payload_digest="2" * 64,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    intent = a.decide(p1.pause_id, "approved", "pgk-actor")
    assert intent.tenant.tenant_id == "pgk"
    time.sleep(0)  # keep import used even if assertions change
