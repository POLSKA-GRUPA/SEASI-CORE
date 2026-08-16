"""Structured logging with the four mandatory correlation fields.

Every log line produced by the kernel carries: ``tenant_id``,
``workflow_id``, ``case_id`` and ``state``. ``None`` is serialized
explicitly so absence is visible, never silent.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_REQUIRED = ("tenant_id", "workflow_id", "case_id", "state")
_CONFIGURED = False


class _DynamicStderr:
    """Always writes to the CURRENT sys.stderr (test-friendly)."""

    def write(self, s: str) -> int:
        return sys.stderr.write(s)

    def flush(self) -> None:
        sys.stderr.flush()


class StructuredFormatter(logging.Formatter):
    """Compact single-line JSON logs, ordered and stable."""

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "seasi_event", record.getMessage()),
            "logger": record.name,
        }
        fields = getattr(record, "seasi_fields", None)
        if isinstance(fields, dict):
            base.update(fields)
        for key in _REQUIRED:
            base.setdefault(key, None)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False, default=str)


def configure_root() -> None:
    """Install the structured formatter once (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=_DynamicStderr())
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger("seasi")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_root()
    return logging.getLogger(f"seasi.{name}")


def log_event(
    logger_name: str,
    event_type: str,
    *,
    tenant_id: str | None,
    workflow_id: str | None = None,
    case_id: str | None = None,
    state: str | None = None,
    **extra: Any,
) -> None:
    """Emit one structured event with the four mandatory fields."""
    logger = get_logger(logger_name)
    fields: dict[str, Any] = {
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "case_id": case_id,
        "state": state,
    }
    fields.update(extra)
    logger.info(
        event_type,
        extra={"seasi_event": event_type, "seasi_fields": fields},
    )
