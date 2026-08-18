"""Contracts v0 (session/artifact/hitl/shell-api): validation behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from seasi_core.contracts.artifacts import Artifact
from seasi_core.contracts.hitl import HitlPause, HitlStatus
from seasi_core.contracts.session import AgentSession, SessionState
from seasi_core.contracts.shell_api import RpcMethodSpec, ShellApiManifest, build_manifest
from seasi_core.contracts.tenant import TenantScope


def _tenant() -> TenantScope:
    return TenantScope(tenant_id="demo")


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=15)


# -- session ------------------------------------------------------------------


def test_session_happy_path() -> None:
    session = AgentSession(
        tenant=_tenant(), client_ref="B00000091", period_ref="2026T3", adapter="pi"
    )
    assert session.state == SessionState.CREATED
    assert session.schema_version == "seasi.session/v1"


@pytest.mark.parametrize("bad_period", ["2026T5", "26T1", "2026", "2026-Q3", ""])
def test_session_rejects_bad_period(bad_period: str) -> None:
    with pytest.raises(ValidationError):
        AgentSession(tenant=_tenant(), client_ref="X", period_ref=bad_period, adapter="pi")


def test_session_rejects_bad_adapter() -> None:
    with pytest.raises(ValidationError):
        AgentSession(tenant=_tenant(), client_ref="X", period_ref="2026T3", adapter="PI!")


# -- artifact -----------------------------------------------------------------


def _digest() -> str:
    return "a" * 64


def test_artifact_accepts_relative_path() -> None:
    artifact = Artifact(
        session_id="00000000-0000-0000-0000-000000000001",
        tenant=_tenant(),
        kind="aeat.model",
        content_hash=_digest(),
        path="clientes/B00000091/2026T3/modelo303.pdf",
    )
    assert artifact.kind == "aeat.model"


@pytest.mark.parametrize(
    "bad_path",
    [
        "/abs/path.pdf",
        "~/home.pdf",
        "a/../b.pdf",
        "a//b.pdf",
        "a/./b.pdf",
    ],
)
def test_artifact_rejects_escape_paths(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        Artifact(
            session_id="00000000-0000-0000-0000-000000000001",
            tenant=_tenant(),
            kind="aeat.model",
            content_hash=_digest(),
            path=bad_path,
        )


def test_artifact_rejects_bad_hash_and_kind() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            session_id="00000000-0000-0000-0000-000000000001",
            tenant=_tenant(),
            kind="notdotted",
            content_hash=_digest(),
            path="ok.pdf",
        )
    with pytest.raises(ValidationError):
        Artifact(
            session_id="00000000-0000-0000-0000-000000000001",
            tenant=_tenant(),
            kind="aeat.model",
            content_hash="XYZ",
            path="ok.pdf",
        )


# -- hitl pause ---------------------------------------------------------------


def _pause(**overrides: object) -> HitlPause:
    base: dict[str, object] = {
        "session_id": "00000000-0000-0000-0000-000000000001",
        "tenant": _tenant(),
        "capability_id": "filing.submit",
        "payload_digest": _digest(),
        "expires_at": _future(),
    }
    base.update(overrides)
    return HitlPause.model_validate(base)


def test_hitl_pending_has_no_decision_fields() -> None:
    pause = _pause()
    assert pause.status == HitlStatus.PENDING
    assert pause.decided_by is None


def test_hitl_rejects_pending_with_decision() -> None:
    with pytest.raises(ValidationError):
        _pause(decided_by="kenyi")


def test_hitl_rejects_decision_without_fields() -> None:
    with pytest.raises(ValidationError):
        _pause(status=HitlStatus.APPROVED)


def test_hitl_expiry_must_follow_creation() -> None:
    with pytest.raises(ValidationError):
        _pause(expires_at=datetime.now(UTC) - timedelta(minutes=1))


# -- shell api ----------------------------------------------------------------


def test_manifest_unique_methods_and_grammar() -> None:
    with pytest.raises(ValidationError):
        ShellApiManifest(
            methods=[
                RpcMethodSpec(name="seasi.version"),
                RpcMethodSpec(name="seasi.version"),
            ]
        )
    with pytest.raises(ValidationError):
        RpcMethodSpec(name="not.seasi.method")


def test_build_manifest_declares_v0_surface() -> None:
    manifest = build_manifest()
    names = {m.name for m in manifest.methods}
    assert names == {
        "seasi.version",
        "seasi.session.start",
        "seasi.session.run",
        "seasi.event.tail",
        "seasi.usage.summary",
        "seasi.hitl.list",
        "seasi.hitl.create",
        "seasi.hitl.decide",
    }
    gated = [m for m in manifest.methods if m.effect_gated]
    assert [m.name for m in gated] == ["seasi.hitl.decide"]
