"""Neutral tenant scoping contract.

Tenancy is the first-class axis of the kernel: every envelope, approval and
execution carries an explicit ``TenantScope``. There is NO default tenant
anywhere; absence of scope must fail closed (see ``kernel.context``).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class TenantScope(BaseModel):
    """Immutable identification of the tenant (and optional case/project refs).

    ``tenant_id`` rules:
    - lowercase, digits, ``.``, ``_`` and ``-``;
    - must start with an alphanumeric character;
    - never empty, never inferred, never defaulted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=64)
    case_ref: str | None = Field(default=None, min_length=1, max_length=128)
    project_ref: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _TENANT_ID.match(normalized):
            raise ValueError(
                f"tenant_id must match '^[a-z0-9][a-z0-9._-]{{0,63}}$' (got {value!r})"
            )
        return normalized

    @field_validator("case_ref", "project_ref")
    @classmethod
    def _strip_refs(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("reference must not be blank")
        return normalized
