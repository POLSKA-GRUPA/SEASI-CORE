"""Process-based harness: spawn an argv, stream JSON-lines as events.

This is the PTY-free base: stdout is read line by line, each line parsed as
JSON when possible (structured events) and kept as a raw message otherwise.
Budgets (deadline/turns) are enforced here, in kernel code — never delegated
to the model's goodwill. Cancellation terminates the process group.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Iterator
from typing import Any

from seasi_core.harness.port import (
    HarnessBudget,
    HarnessEvent,
    HarnessEventKind,
    SessionSpec,
)

_KNOWN_KINDS = {kind.value for kind in HarnessEventKind}


class HarnessFailure(RuntimeError):
    """Process-level failure (non-zero exit, budget exceeded)."""


class ProcessHarness:
    """Adapter base over ``subprocess.Popen`` with budget enforcement."""

    name: str

    def __init__(
        self,
        name: str,
        argv_builder: Callable[[SessionSpec], list[str]],
        *,
        timeout_grace_s: float = 2.0,
    ) -> None:
        self.name = name
        self._argv_builder = argv_builder
        self._timeout_grace_s = timeout_grace_s
        self._proc: subprocess.Popen[str] | None = None
        self._cancelled = False

    # -- port implementation ----------------------------------------------------

    def start(
        self, spec: SessionSpec, budget: HarnessBudget | None = None
    ) -> Iterator[HarnessEvent]:
        argv = self._argv_builder(spec)
        self._cancelled = False
        self._proc = subprocess.Popen(
            argv,
            cwd=str(spec.cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        # Capture handles before any yield: a cancel() between generator
        # resumes nulls _proc, but the loop must keep draining captured pipes.
        proc = self._proc
        assert proc is not None
        stdout = proc.stdout
        assert stdout is not None
        yield self._event(spec, HarnessEventKind.SPAWNED, {"argv": argv})

        turns = 0
        started = time.monotonic()
        try:
            try:
                for line in stdout:
                    if self._cancelled:
                        break
                    event = self._parse_line(spec, line.rstrip("\n"))
                    if event.kind in (HarnessEventKind.MESSAGE, HarnessEventKind.TOOL_CALL):
                        turns += 1
                    yield event
                    if budget is not None and self._budget_exceeded(budget, turns, started):
                        self.cancel()
                        yield self._event(
                            spec, HarnessEventKind.FAILED, {"reason": "budget_exceeded"}
                        )
                        return
            except ValueError:
                pass  # stdout closed underneath us by cancel()
            if self._cancelled:
                yield self._event(spec, HarnessEventKind.CANCELLED, {})
                return
            returncode = proc.wait()
            kind = HarnessEventKind.COMPLETED if returncode == 0 else HarnessEventKind.FAILED
            yield self._event(spec, kind, {"returncode": returncode})
        finally:
            self._cleanup()

    def cancel(self) -> None:
        self._cancelled = True
        self._cleanup()

    # -- internals ---------------------------------------------------------------

    def _budget_exceeded(self, budget: HarnessBudget, turns: int, started: float) -> bool:
        if budget.max_turns is not None and turns >= budget.max_turns:
            return True
        return bool(
            budget.deadline_s is not None and (time.monotonic() - started) > budget.deadline_s
        )

    def _parse_line(self, spec: SessionSpec, line: str) -> HarnessEvent:
        try:
            payload: Any = json.loads(line)
        except json.JSONDecodeError:
            return self._event(spec, HarnessEventKind.MESSAGE, {"raw": line})
        if isinstance(payload, dict):
            kind_raw = str(payload.get("type", "message"))
            if kind_raw in _KNOWN_KINDS:
                kind = HarnessEventKind(kind_raw)
            else:
                kind = HarnessEventKind.MESSAGE
            data = {k: v for k, v in payload.items() if k != "type"}
            return self._event(spec, kind, data)
        return self._event(spec, HarnessEventKind.MESSAGE, {"raw": line})

    def _event(
        self, spec: SessionSpec, kind: HarnessEventKind, data: dict[str, object]
    ) -> HarnessEvent:
        return HarnessEvent(kind=kind, session_id=spec.session_id, adapter=self.name, data=data)

    def _cleanup(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=self._timeout_grace_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()
        self._proc = None
