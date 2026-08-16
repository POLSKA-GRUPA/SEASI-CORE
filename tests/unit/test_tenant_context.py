"""Unit tests: fail-closed tenant context."""

import pytest

from seasi_core.contracts.tenant import TenantScope
from seasi_core.kernel.context import (
    TenantContextError,
    current_tenant,
    tenant_scope,
    try_current_tenant,
)


def test_missing_scope_raises() -> None:
    with pytest.raises(TenantContextError):
        current_tenant()


def test_try_current_tenant_returns_none() -> None:
    assert try_current_tenant() is None


def test_scope_binds_and_restores() -> None:
    scope = TenantScope(tenant_id="acme", case_ref="case-1")
    with tenant_scope(scope):
        assert current_tenant().tenant_id == "acme"
        assert current_tenant().case_ref == "case-1"
    assert try_current_tenant() is None


def test_scope_nesting_inner_wins() -> None:
    outer = TenantScope(tenant_id="acme")
    inner = TenantScope(tenant_id="beta")
    with tenant_scope(outer):
        with tenant_scope(inner):
            assert current_tenant().tenant_id == "beta"
        assert current_tenant().tenant_id == "acme"


def test_scope_reset_on_exception() -> None:
    scope = TenantScope(tenant_id="acme")
    with pytest.raises(RuntimeError), tenant_scope(scope):
        raise RuntimeError("boom")
    assert try_current_tenant() is None


def test_tenant_id_normalization_and_validation() -> None:
    assert TenantScope(tenant_id="  ACME ").tenant_id == "acme"
    with pytest.raises(ValueError):
        TenantScope(tenant_id="")
    with pytest.raises(ValueError):
        TenantScope(tenant_id="_leading-underscore")
    with pytest.raises(ValueError):
        TenantScope(tenant_id="has spaces")


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValueError):
        TenantScope(tenant_id="acme", franchise_id="1")  # type: ignore[call-arg]
