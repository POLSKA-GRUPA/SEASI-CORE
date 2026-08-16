"""Generic versioned registry used for capabilities, modules, workflows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Generic, TypeVar

from seasi_core.contracts.capabilities import CapabilitySpec
from seasi_core.contracts.workflows import WorkflowDefinition

T = TypeVar("T")


class RegistrationError(KeyError):
    """Base error for registry misuse."""


class DuplicateRegistrationError(RegistrationError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key

    def __str__(self) -> str:
        return f"duplicate registration: {self.key!r}"


class UnknownKeyError(RegistrationError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key

    def __str__(self) -> str:
        return f"unknown key: {self.key!r}"


class Registry(Generic[T]):
    """Append-only, deterministic registry.

    - keys are non-empty strings;
    - duplicate registration is an error (no silent overwrite);
    - lookup of unknown keys is an error (fail-closed);
    - ``snapshot`` returns an immutable view for iteration.
    """

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, key: str, value: T) -> None:
        key = self._normalize(key)
        if key in self._items:
            raise DuplicateRegistrationError(key)
        self._items[key] = value

    def get(self, key: str) -> T:
        key = self._normalize(key)
        try:
            return self._items[key]
        except KeyError:
            raise UnknownKeyError(key) from None

    def snapshot(self) -> Mapping[str, T]:
        return MappingProxyType(dict(self._items))

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._normalize(key) in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    @staticmethod
    def _normalize(key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise RegistrationError("registry key must not be blank")
        return normalized


class ActionRegistry(Registry[CapabilitySpec]):
    """Registry of ``CapabilitySpec`` objects; the governed action catalog."""


class WorkflowRegistry(Registry[WorkflowDefinition]):
    """Registry of ``WorkflowDefinition`` objects with checksum access."""

    def checksum(self, workflow_id: str) -> str:
        return self.get(workflow_id).checksum()
