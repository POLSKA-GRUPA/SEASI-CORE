"""Filesystem scope guard: tenant confinement enforced by code, not prompts.

Every path a session may touch resolves under ``<root>/<tenant_id>/``. The
guard is the partial-application defence against prompt injection: even if a
model emits an absolute path or a traversal, the kernel refuses it here.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ScopeViolation(Exception):
    """Raised when a path would escape the tenant scope (fail-closed)."""


class TenantPathGuard(BaseModel):
    """Deterministic path confinement for one tenant under a kernel-managed root.

    The model is immutable and hashable so services can build one guard per
    ``TenantScope`` and pass it around freely.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    root: Path
    tenant_id: str

    @property
    def base(self) -> Path:
        return self.root / self.tenant_id

    def resolve(self, relative: str) -> Path:
        """Resolve a RELATIVE path inside the tenant base; reject escapes."""
        if relative.startswith(("/", "~")) or "\\" in relative:
            raise ScopeViolation(f"path must be relative: {relative!r}")
        if relative in ("", "."):
            raise ScopeViolation("path must name something inside the tenant scope")
        segments = relative.split("/")
        if any(seg in ("", ".", "..") for seg in segments):
            raise ScopeViolation(f"path traversal rejected: {relative!r}")
        candidate = (self.base.joinpath(*segments)).resolve(strict=False)
        base_resolved = self.base.resolve(strict=False)
        if base_resolved != candidate and base_resolved not in candidate.parents:
            raise ScopeViolation(f"resolved path escapes tenant scope: {relative!r}")
        return candidate

    def ensure(self, path: Path) -> Path:
        """Verify an ABSOLUTE path stays under the tenant base after resolution."""
        resolved = path.resolve(strict=False)
        base_resolved = self.base.resolve(strict=False)
        if resolved != base_resolved and base_resolved not in resolved.parents:
            raise ScopeViolation(f"absolute path escapes tenant scope: {path!r}")
        return resolved

    def session_dir(self, session_id: str) -> Path:
        return self.base / "sessions" / session_id
