"""``python -m seasi_core.rpc`` — stdio JSON-RPC entrypoint for the shell.

Environment:

    SEASI_DB    path to the ledger SQLite file   (default: ~/.seasi/ledger.db)
    SEASI_ROOT  tenant-scoped workspace root     (default: ~/.seasi/workspace)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from seasi_core.ledger.hitl import HitlStore
from seasi_core.ledger.store import EventLedger
from seasi_core.rpc.methods import build_dispatcher
from seasi_core.rpc.server import serve_stdio
from seasi_core.services.sessions import SessionService


def _default_home() -> Path:
    return Path.home() / ".seasi"


def main() -> int:
    home = _default_home()
    db_path = Path(os.environ.get("SEASI_DB", str(home / "ledger.db")))
    root = Path(os.environ.get("SEASI_ROOT", str(home / "workspace"))).resolve()
    root.mkdir(parents=True, exist_ok=True)

    ledger = EventLedger(db_path)
    sessions = SessionService(ledger=ledger, root=root)
    hitl = HitlStore(ledger=ledger)
    dispatcher = build_dispatcher(ledger=ledger, sessions=sessions, hitl=hitl)
    sys.stderr.write(
        f"[seasi-rpc] serving on stdio (db={db_path}, root={root})\n"
    )
    sys.stderr.flush()
    serve_stdio(dispatcher)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
