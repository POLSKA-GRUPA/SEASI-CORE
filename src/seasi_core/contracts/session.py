"""Agent session contract for the despacho shell.

A session binds one tenant scope, one client reference (e.g. NIF), one
period (trimestre) and the harness adapter that will execute it. Sessions
are the unit of isolation, evidence and billing in the ledger.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from seasi_core.contracts.tenant import TenantScope

SCHEMA_VERSION = "seasi.session/v1"

PERIOD_REF = re.compile(r"^\d{4}T[1-4]$")
ADAPTER_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MODEL_REF = re.compile(r"^[a-z0-9][a-z0-9/._:+-]{0,127}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SessionState(StrEnum):
    """Lifecycle states; ``paused_hitl`` means a governed effect awaits approval."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED_HITL = "paused_hitl"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentSession(BaseModel):
    """Immutable session record; state transitions are ledger events, not edits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default=SCHEMA_VERSION)
    tenant: TenantScope
    client_ref: str = Field(min_length=1, max_length=64)
    period_ref: str = Field(min_length=4, max_length=6)
    adapter: str = Field(min_length=1, max_length=32)
    model_ref: str | None = Field(default=None, min_length=1, max_length=128)
    state: SessionState = SessionState.CREATED
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("period_ref")
    @classmethod
    def _validate_period(cls, value: str) -> str:
        if not PERIOD_REF.match(value):
            raise ValueError("period_ref must look like '2026T3' (YYYYT[1-4])")
        return value

    @field_validator("adapter")
    @classmethod
    def _validate_adapter(cls, value: str) -> str:
        if not ADAPTER_NAME.match(value):
            raise ValueError("adapter must match '^[a-z][a-z0-9_-]{0,31}$'")
        return value

    @field_validator("model_ref")
    @classmethod
    def _validate_model_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not MODEL_REF.match(value):
            raise ValueError("model_ref must be a provider/model identifier")
        return value

    @model_validator(mode="after")
    def _updated_not_before_created(self) -> AgentSession:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self
