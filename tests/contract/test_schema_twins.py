"""The shipped JSON Schemas must stay in lockstep with the Pydantic contracts.

These tests derive the expected shape from ``model_json_schema()`` so that
adding, removing, or renaming a field on a contract without bumping the
shipped twin fails CI, and validate a real serialized instance against the
shipped file so the twin is known to accept what the kernel emits.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest

from seasi_core.contracts.events import EventEnvelope
from seasi_core.contracts.evidence import ApprovalIntent
from seasi_core.contracts.tenant import TenantScope

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "v1"

TWINS = [
    (TenantScope, "tenant-scope.schema.json"),
    (ApprovalIntent, "approval-intent.schema.json"),
    (EventEnvelope, "event-envelope.schema.json"),
]


def _shipped(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text())


@pytest.mark.parametrize(("model", "filename"), TWINS)
def test_twin_properties_match_model(model, filename) -> None:
    shipped = _shipped(filename)
    derived = model.model_json_schema()
    assert set(shipped["properties"]) == set(derived["properties"]), (
        f"{filename} property set drifted from {model.__name__}"
    )


@pytest.mark.parametrize(("model", "filename"), TWINS)
def test_twin_required_match_model(model, filename) -> None:
    shipped = _shipped(filename)
    derived = model.model_json_schema()
    assert set(shipped.get("required", [])) == set(derived.get("required", [])), (
        f"{filename} required set drifted from {model.__name__}"
    )


@pytest.mark.parametrize(("model", "filename"), TWINS)
def test_twin_is_closed(model, filename) -> None:
    assert _shipped(filename).get("additionalProperties") is False


def test_shipped_schema_accepts_real_tenant_scope() -> None:
    scope = TenantScope(tenant_id="acme", case_ref="c-1")
    instance = json.loads(scope.model_dump_json())
    jsonschema.validate(instance, _shipped("tenant-scope.schema.json"))


def test_shipped_schema_accepts_real_approval_intent() -> None:
    now = datetime.now(UTC)
    intent = ApprovalIntent(
        intent_id=uuid4(),
        tenant=TenantScope(tenant_id="acme", case_ref="c-1"),
        capability_id="ledger.dispatch",
        payload_digest="a" * 64,
        actor="runner",
        nonce="nonce-0001",
        created_at=now,
        expires_at=now.replace(year=now.year + 1),
    )
    instance = json.loads(intent.model_dump_json())
    # The shipped $ids are relative URIs, so inline the tenant twin instead of
    # relying on $ref resolution semantics.
    schema = _shipped("approval-intent.schema.json")
    tenant_twin = {
        k: v for k, v in _shipped("tenant-scope.schema.json").items() if not k.startswith("$")
    }
    schema["properties"]["tenant"] = tenant_twin
    jsonschema.validate(instance, schema)
