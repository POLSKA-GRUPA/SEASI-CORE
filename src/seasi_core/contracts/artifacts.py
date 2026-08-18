"""Artifact contract: verifiable outputs produced inside a session.

Artifacts (AEAT model drafts, email drafts, Excel imports, reports) always
carry a content hash and a RELATIVE path confined to the tenant scope.
Absolute paths or traversal segments are rejected at the contract level;
the kernel scope guard enforces the same at filesystem level.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from seasi_core.contracts.tenant import TenantScope

SCHEMA_VERSION = "seasi.artifact/v1"

KIND_GRAMMAR = re.compile(r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Artifact(BaseModel):
    """Immutable artifact reference; content lives at ``path`` under the tenant root."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID = Field(default_factory=uuid4)
    schema_version: str = Field(default=SCHEMA_VERSION)
    session_id: UUID
    tenant: TenantScope
    kind: str = Field(min_length=3, max_length=64)
    content_hash: str = Field(min_length=64, max_length=64)
    path: str = Field(min_length=1, max_length=512)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if not KIND_GRAMMAR.match(value):
            raise ValueError("kind must be dotted lowercase, e.g. 'aeat.model'")
        return value

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        if not _SHA256.match(value):
            raise ValueError("content_hash must be a lowercase sha-256 hex digest")
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if value.startswith(("/", "~")) or "\\" in value:
            raise ValueError("path must be relative to the tenant scope")
        segments = value.split("/")
        if any(seg in ("", ".", "..") for seg in segments):
            raise ValueError("path must not contain empty, '.' or '..' segments")
        return value
