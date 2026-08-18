"""JSON-RPC 2.0 server over line-delimited stdio.

This is the ONLY business channel between the despacho shell and the
kernel. Transport rules (fail-closed):

* malformed JSON            -> -32700
* not a valid request shape -> -32600
* method not in manifest    -> -32601 (single source: ShellApiManifest)
* params fail the model     -> -32602
* anything else             -> -32603 (no internal details leaked)

Notifications (no ``id``) are processed silently. Batches are rejected in v0.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import IO, Any

from pydantic import BaseModel, ValidationError

from seasi_core.contracts.shell_api import ShellErrorCode, rpc_error_payload

Handler = Callable[..., Any]
Notify = Callable[[str, dict[str, Any]], None]


def _accepts_notify(handler: Handler) -> bool:
    """True si el handler declara parámetro ``notify`` (streaming opcional)."""
    import inspect

    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    return "notify" in sig.parameters


class RpcError(Exception):
    """Typed transport error carrying a JSON-RPC code."""

    def __init__(self, code: ShellErrorCode, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class Dispatcher:
    """Method table with per-method pydantic params validation."""

    def __init__(self) -> None:
        self._handlers: dict[str, tuple[type[BaseModel] | None, Handler]] = {}

    def register(
        self, method: str, handler: Handler, params_model: type[BaseModel] | None = None
    ) -> None:
        self._handlers[method] = (params_model, handler)

    def methods(self) -> list[str]:
        return sorted(self._handlers)

    def call(
        self,
        method: str,
        params: Any,
        notify: Notify | None = None,
    ) -> Any:
        entry = self._handlers.get(method)
        if entry is None:
            raise RpcError(ShellErrorCode.METHOD_NOT_FOUND, f"unknown method {method!r}")
        params_model, handler = entry
        if params_model is None:
            if params not in (None, {}):
                raise RpcError(ShellErrorCode.INVALID_PARAMS, f"{method} takes no params")
            return handler({}, notify) if _accepts_notify(handler) else handler({})
        if not isinstance(params, dict):
            raise RpcError(ShellErrorCode.INVALID_PARAMS, "params must be an object")
        try:
            validated = params_model.model_validate(params)
        except ValidationError as exc:
            raise RpcError(
                ShellErrorCode.INVALID_PARAMS, "invalid params", data=exc.errors(include_url=False)
            ) from exc
        dumped = validated.model_dump()
        return handler(dumped, notify) if _accepts_notify(handler) else handler(dumped)


def _make_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_error(
    request_id: Any, code: ShellErrorCode, message: str, data: Any = None
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": rpc_error_payload(code, message, data),
    }


def _validate_request(payload: Any) -> tuple[str, Any, Any]:
    if not isinstance(payload, dict):
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "request must be an object")
    if payload.get("jsonrpc") != "2.0":
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "jsonrpc must be '2.0'")
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "method must be a non-empty string")
    if (
        "params" in payload
        and payload["params"] is not None
        and not isinstance(payload.get("params"), (dict, list))
    ):
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "params must be object or array")
    if isinstance(payload.get("params"), list):
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "positional params unsupported in v0")
    request_id = payload.get("id")
    if request_id is not None and not isinstance(request_id, (str, int)):
        raise RpcError(ShellErrorCode.INVALID_REQUEST, "id must be string or integer")
    return method, payload.get("params"), request_id


def serve(reader: IO[str], writer: IO[str], dispatcher: Dispatcher) -> None:
    """Blocking loop: read one JSON per line, write one response per line.

    Handlers MAY stream server notifications (``method``-only lines) while a
    request is in flight: they are written BEFORE the final response line,
    preserving strict per-request wire ordering.
    """
    for raw_line in reader:
        line = raw_line.strip()
        if not line:
            continue
        request_id: Any = None

        def notify(method: str, params: dict[str, Any]) -> None:
            writer.write(
                json.dumps(
                    {"jsonrpc": "2.0", "method": method, "params": params},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
            writer.flush()

        try:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                response = _make_error(None, ShellErrorCode.PARSE_ERROR, "parse error")
                _ = exc
            else:
                method, params, request_id = _validate_request(payload)
                try:
                    result = dispatcher.call(method, params, notify)
                    if request_id is None:
                        continue  # notification: processed, no response
                    response = _make_response(request_id, result)
                except RpcError as rpc_exc:
                    if request_id is None:
                        continue
                    response = _make_error(request_id, rpc_exc.code, rpc_exc.message, rpc_exc.data)
                except Exception:
                    if request_id is None:
                        continue
                    response = _make_error(
                        request_id,
                        ShellErrorCode.INTERNAL_ERROR,
                        "internal error",
                        data={"error": "internal"},
                    )
        except RpcError as envelope_exc:
            response = _make_error(None, envelope_exc.code, envelope_exc.message)
        writer.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
        writer.flush()


def serve_stdio(dispatcher: Dispatcher) -> None:
    import sys

    serve(sys.stdin, sys.stdout, dispatcher)
