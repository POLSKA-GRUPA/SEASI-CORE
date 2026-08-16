"""Fail-closed tenant context.

The golden rule of the kernel: THERE IS NO DEFAULT TENANT.

Any code path that needs a tenant must either receive an explicit
``TenantScope`` or call ``current_tenant()`` inside a ``tenant_scope``
block. If the scope is absent, ``TenantContextError`` is raised — never
fallback, never "1", never env vars.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from seasi_core.contracts.tenant import TenantScope

_current_tenant: ContextVar[TenantScope | None] = ContextVar("seasi_current_tenant", default=None)


class TenantContextError(RuntimeError):
    """Raised when a tenant is required but absent (fail-closed)."""


def current_tenant() -> TenantScope:
    """Return the active tenant scope or raise ``TenantContextError``."""
    scope = _current_tenant.get()
    if scope is None:
        raise TenantContextError(
            "no active tenant scope: wrap the call in tenant_scope(...) "
            "or pass an explicit TenantScope"
        )
    return scope


def try_current_tenant() -> TenantScope | None:
    """Non-raising variant for optional context enrichment."""
    return _current_tenant.get()


@contextmanager
def tenant_scope(scope: TenantScope) -> Iterator[TenantScope]:
    """Bind a tenant for the duration of the block; restore afterwards."""
    token: Token[TenantScope | None] = _current_tenant.set(scope)
    try:
        yield scope
    finally:
        _current_tenant.reset(token)
