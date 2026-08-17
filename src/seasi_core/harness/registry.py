"""Adapter registry: fail-closed lookup of harness runtimes by name."""

from __future__ import annotations

from collections.abc import Callable

from seasi_core.harness.pi_adapter import PiHarness
from seasi_core.harness.port import HarnessAdapter
from seasi_core.harness.process import ProcessHarness


class UnknownAdapter(Exception):
    """No adapter registered under the requested name (fail-closed)."""


Factory = Callable[[], HarnessAdapter]

_FACTORIES: dict[str, Factory] = {}


def register(name: str, factory: Factory) -> None:
    _FACTORIES[name] = factory


def build(name: str) -> HarnessAdapter:
    factory = _FACTORIES.get(name)
    if factory is None:
        msg = f"unknown harness adapter {name!r}; registered: {sorted(_FACTORIES)}"
        raise UnknownAdapter(msg)
    return factory()


def registered_names() -> list[str]:
    return sorted(_FACTORIES)


def _install_defaults() -> None:
    if "pi" not in _FACTORIES:
        register("pi", PiHarness)


_install_defaults()

__all__ = [
    "ProcessHarness",
    "UnknownAdapter",
    "build",
    "register",
    "registered_names",
]
