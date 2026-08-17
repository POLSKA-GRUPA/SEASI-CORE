"""Shell API manifest and JSON-RPC error contract.

The despacho shell talks to the kernel exclusively through the JSON-RPC 2.0
methods declared in the ``ShellApiManifest``. Anything not declared is
rejected fail-closed (METHOD_NOT_FOUND). ``effect_gated`` flags methods that
can only resolve through an approved ``ApprovalIntent``.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "seasi/shell-api/v1"

METHOD_GRAMMAR = re.compile(r"^seasi\.[a-z0-9][a-z0-9_.]*$")
SCHEMA_REF = re.compile(r"^seasi/[a-z0-9-]+/v1$")


class ShellErrorCode(IntEnum):
    """JSON-RPC 2.0 standard codes plus SEASI fail-closed domain codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    SEASI_FAIL_CLOSED = 100
    SEASI_TENANT_SCOPE = 101
    SEASI_EFFECT_UNAPPROVED = 102
    SEASI_UNKNOWN_ADAPTER = 103


class RpcMethodSpec(BaseModel):
    """One declared RPC method with optional schema references."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=6, max_length=96)
    params_schema_ref: str | None = Field(default=None, min_length=8, max_length=64)
    result_schema_ref: str | None = Field(default=None, min_length=8, max_length=64)
    effect_gated: bool = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not METHOD_GRAMMAR.match(value):
            raise ValueError("method names must look like 'seasi.session.start'")
        return value

    @field_validator("params_schema_ref", "result_schema_ref")
    @classmethod
    def _validate_refs(cls, value: str | None) -> str | None:
        if value is not None and not SCHEMA_REF.match(value):
            raise ValueError("schema refs must look like 'seasi/session/v1'")
        return value


class ShellApiManifest(BaseModel):
    """The complete, versioned surface the shell may call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION)
    methods: list[RpcMethodSpec] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _unique_methods(self) -> ShellApiManifest:
        names = [m.name for m in self.methods]
        if len(names) != len(set(names)):
            raise ValueError("method names must be unique")
        return self

    def method(self, name: str) -> RpcMethodSpec | None:
        return next((m for m in self.methods if m.name == name), None)


def build_manifest() -> ShellApiManifest:
    """The v0 method surface implemented by ``seasi_core.rpc.methods``."""
    return ShellApiManifest(
        methods=[
            RpcMethodSpec(name="seasi.version"),
            RpcMethodSpec(
                name="seasi.session.start",
                params_schema_ref="seasi/session/v1",
                result_schema_ref="seasi/session/v1",
            ),
            RpcMethodSpec(name="seasi.session.run"),
            RpcMethodSpec(name="seasi.event.tail"),
            RpcMethodSpec(
                name="seasi.hitl.list",
                result_schema_ref="seasi/hitl-pause/v1",
            ),
            RpcMethodSpec(
                name="seasi.hitl.create",
                params_schema_ref="seasi/hitl-pause/v1",
            ),
            RpcMethodSpec(
                name="seasi.hitl.decide",
                params_schema_ref="seasi/hitl-pause/v1",
                effect_gated=True,
            ),
        ]
    )


def rpc_error_payload(code: ShellErrorCode, message: str, data: Any = None) -> dict[str, Any]:
    """Canonical JSON-RPC error object."""
    err: dict[str, Any] = {"code": int(code), "message": message}
    if data is not None:
        err["data"] = data
    return err
