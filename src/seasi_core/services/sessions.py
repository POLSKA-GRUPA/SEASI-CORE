"""Kernel services used by the RPC surface (thin, ledger-backed)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from seasi_core.contracts.events import build_event
from seasi_core.contracts.session import AgentSession, SessionState
from seasi_core.contracts.tenant import TenantScope
from seasi_core.harness import (
    HarnessBudget,
    HarnessEvent,
    HarnessEventKind,
    SessionSpec,
    build,
)
from seasi_core.harness.registry import UnknownAdapter
from seasi_core.kernel.scope_guard import ScopeViolation, TenantPathGuard
from seasi_core.ledger.store import EventLedger

SESSION_CREATED = "session.created"
SESSION_STATE_PREFIX = "session.state."


class SessionError(Exception):
    """Fail-closed session lifecycle violations."""


class SessionService(BaseModel):
    """Create sessions, run harness turns, persist everything to the ledger."""

    model_config = {"arbitrary_types_allowed": True}

    ledger: EventLedger
    root: Path

    def start(
        self,
        tenant: TenantScope,
        client_ref: str,
        period_ref: str,
        adapter: str = "pi",
        model_ref: str | None = None,
    ) -> AgentSession:
        try:
            harness = build(adapter)
        except UnknownAdapter as exc:
            msg = f"adapter {adapter!r} is not registered"
            raise SessionError(msg) from exc
        session = AgentSession(
            tenant=tenant,
            client_ref=client_ref,
            period_ref=period_ref,
            adapter=harness.name,
            model_ref=model_ref,
        )
        self.ledger.append(
            build_event(SESSION_CREATED, tenant, session.model_dump(mode="json"))
        )
        return session

    def run(
        self,
        session: AgentSession,
        prompt: str,
        budget: HarnessBudget | None = None,
        on_event: Callable[[HarnessEvent], None] | None = None,
    ) -> list[HarnessEvent]:
        guard = TenantPathGuard(root=self.root, tenant_id=session.tenant.tenant_id)
        cwd = guard.session_dir(str(session.session_id))
        cwd.mkdir(parents=True, exist_ok=True)
        self._transition(session, SessionState.RUNNING)
        spec = SessionSpec(
            session_id=session.session_id,
            tenant=session.tenant,
            prompt=prompt,
            cwd=cwd,
            model_ref=session.model_ref,
        )
        harness = build(session.adapter)
        events: list[HarnessEvent] = []
        try:
            for event in harness.start(spec, budget):
                self.ledger.append(
                    build_event(
                        f"harness.{event.kind.value}",
                        session.tenant,
                        {
                            "session_id": str(session.session_id),
                            "adapter": event.adapter,
                            "data": event.data,
                        },
                    )
                )
                events.append(event)
                if on_event is not None:
                    on_event(event)
        except ScopeViolation as exc:
            self._transition(session, SessionState.FAILED)
            msg = f"session {session.session_id} escaped tenant scope"
            raise SessionError(msg) from exc
        terminal_kind = events[-1].kind if events else HarnessEventKind.FAILED
        if terminal_kind == HarnessEventKind.COMPLETED:
            self._transition(session, SessionState.COMPLETED)
        elif terminal_kind in (HarnessEventKind.FAILED, HarnessEventKind.CANCELLED):
            self._transition(session, SessionState.FAILED)
        return events

    def _transition(self, session: AgentSession, state: SessionState) -> None:
        self.ledger.append(
            build_event(
                f"{SESSION_STATE_PREFIX}{state.value}",
                session.tenant,
                {"session_id": str(session.session_id), "state": state.value},
            )
        )
