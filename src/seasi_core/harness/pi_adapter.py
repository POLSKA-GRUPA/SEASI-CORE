"""pi adapter: today's harness runtime, spawned headless in tenant scope.

Flags verified against ``pi --help`` (pi coding agent):

    pi --mode json --print            one-shot, JSON output lines
    pi --session-id <id>              resume/create an exact session id
    pi --session-dir <dir>            session storage under the tenant root

Streaming/steering via ``--mode rpc`` is the v1 path; v0 is one-shot with
budget enforcement in ``ProcessHarness``. The binary is resolved from
``SEASI_PI_BIN`` (default ``pi``) so tests can substitute a fake script.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from seasi_core.harness.port import SessionSpec
from seasi_core.harness.process import ProcessHarness


def pi_bin() -> str:
    return os.environ.get("SEASI_PI_BIN", "pi")


def pi_argv(bin_override: str | None = None) -> Callable[[SessionSpec], list[str]]:
    executable = bin_override or pi_bin()

    def build(spec: SessionSpec) -> list[str]:
        sessions_dir = spec.cwd / ".pi-sessions"
        argv = [
            executable,
            "--mode",
            "json",
            "--print",
            "--session-id",
            str(spec.session_id),
            "--session-dir",
            str(sessions_dir),
            "--name",
            f"seasi-{spec.tenant.tenant_id}",
        ]
        if spec.model_ref is not None:
            argv.extend(["--model", spec.model_ref])
        argv.extend(spec.extra_args)
        argv.append(spec.prompt)
        return argv

    return build


class PiHarness(ProcessHarness):
    """Concrete pi adapter registered under the name ``pi``."""

    def __init__(self, bin_override: str | None = None) -> None:
        super().__init__("pi", pi_argv(bin_override))
