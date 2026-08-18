"""Harness port: the runtime-agnostic contract every adapter implements.

pi (today) and ASIN (tomorrow) both speak THIS interface; the despacho shell
and kernel services never import a concrete runtime. Business data flows as
structured events; any PTY/terminal output is presentation-only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from seasi_core.contracts.tenant import TenantScope

SCHEMA_VERSION = "seasi.harness/v1"
ADAPTER_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HarnessEventKind(StrEnum):
    SPAWNED = "spawned"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    HITL_REQUIRED = "hitl_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HarnessEvent(BaseModel):
    """One structured event from a harness run (JSON-friendly, ledger-ready)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HarnessEventKind
    session_id: UUID
    adapter: str = Field(min_length=1, max_length=32)
    data: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_utc_now)


class HarnessBudget(BaseModel):
    """Hard limits enforced by the kernel side, not trusted to the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_turns: int | None = Field(default=None, ge=1, le=10_000)
    max_tokens: int | None = Field(default=None, ge=1)
    deadline_s: float | None = Field(default=None, gt=0, le=86_400)


class SessionSpec(BaseModel):
    """Everything an adapter needs to run one session inside the tenant scope."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    session_id: UUID
    tenant: TenantScope
    prompt: str = Field(min_length=1, max_length=1_000_000)
    cwd: Path
    model_ref: str | None = None
    extra_args: tuple[str, ...] = ()


@runtime_checkable
class HarnessAdapter(Protocol):
    """The port. Implementations spawn processes, translate, and enforce scope."""

    name: str

    def start(
        self, spec: SessionSpec, budget: HarnessBudget | None = None
    ) -> Iterator[HarnessEvent]: ...

    def cancel(self) -> None: ...
