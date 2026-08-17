"""Drift gate: schemas/v1 must be in sync with pydantic contracts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "export_schemas.py"


def _load_tool() -> object:
    spec = importlib.util.spec_from_file_location("export_schemas", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_schemas"] = module
    spec.loader.exec_module(module)
    return module


def test_schemas_in_sync_with_contracts() -> None:
    tool = _load_tool()
    assert tool.check_mode() == 0  # type: ignore[attr-defined]
