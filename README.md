# SEASI-CORE

**Neutral multi-tenant kernel for governed agentic workflows in professional services.**

SEASI-CORE is the execution and governance kernel of the SEASI platform: it
owns **contracts, tenancy, Human-in-the-Loop authority and a deterministic
neutral runner**. Domain intelligence — accounting, fiscal, payroll,
marketing — lives in separate private modules that plug into this kernel.

```text
                     ┌─────────────────────────────┐
                     │  agent harness (any, via     │
                     │  versioned contracts)        │
                     └──────────────┬──────────────┘
                                    │
                     ┌──────────────▼──────────────┐
                     │        SEASI-CORE           │
                     │  tenant · contracts · HITL  │
                     │  registries · neutral runner│
                     │  events · evidence          │
                     └──┬──────────┬──────────┬────┘
                        │          │          │
              ┌─────────▼───┐ ┌────▼─────┐ ┌──▼─────────┐
              │ GESTIÓN     │ │ CONTA-   │ │ MARKETING  │
              │ AUTÓNOMA    │ │ LABORAL  │ │ module     │
              │ module      │ │ module   │ │ (private)  │
              │ (private)   │ │ (private)│ │            │
              └─────────────┘ └──────────┘ └────────────┘
                        │          │          │
                     external systems of record
                  (ledgers, banks, AEAT, social platforms)
```

## Why

Professional-service firms (gestorías, agencies, advisors) need agentic
automation that is **auditable by construction**:

- no implicit tenant — every operation is scoped, fail-closed;
- no unreviewed external effect — mutations require a sealed human
  approval bound to the exact payload digest;
- no hidden orchestration — deterministic runner, typed events,
  evidence with content digests;
- no vendor lock-in — the kernel is harness-neutral and module-based.

## The six kernel contracts

| Contract | Purpose |
|---|---|
| `TenantScope` | Mandatory tenant (+ optional case/project refs). No defaults, ever. |
| `CapabilitySpec` | Versioned, dot-namespaced capability with declared effect class. |
| `EffectPolicy` | Fail-closed rules: reads/drafts run; mutations need verified approval. |
| `ApprovalIntent` | Human approval sealed to tenant + capability + SHA-256 payload digest, with expiry and nonce. |
| `WorkflowDefinition` | Immutable, revisioned state machine with deterministic checksum. |
| `EventEnvelope` | Versioned events with correlation, causation and payload digest. |

Effect classes:

```text
READ              → observable, no state change
LOCAL_DRAFT       → creates/updates drafts inside the tenant boundary
EXTERNAL_MUTATION → touches an external system of record; ALWAYS gated
                    behind a verified ApprovalIntent
```

## Quickstart

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this-repo> && cd SEASI-CORE
uv sync --all-groups
uv run pytest -q
```

Minimal governed workflow:

```python
from seasi_core.contracts.tenant import TenantScope
from seasi_core.contracts.capabilities import CapabilitySpec, EffectClass, ApprovalPolicy
from seasi_core.contracts.workflows import (
    WorkflowDefinition,
    StateSpec,
    TransitionSpec,
    ActionCall,
)
from seasi_core.kernel.registry import ActionRegistry
from seasi_core.orchestration.runner import NeutralRunner

actions = ActionRegistry()
actions.register(
    "ledger.dispatch",
    CapabilitySpec(
        capability_id="ledger.dispatch",
        version="1.0.0",
        effect=EffectClass.EXTERNAL_MUTATION,
        approval=ApprovalPolicy.REQUIRED,
    ),
)

workflow = WorkflowDefinition(
    workflow_id="case.dispatch",
    revision=1,
    initial_state="review",
    states=(StateSpec(name="review"), StateSpec(name="done", terminal=True)),
    transitions=(
        TransitionSpec(
            from_state="review",
            to_state="done",
            action=ActionCall(capability_id="ledger.dispatch", input={"entry": "e-1"}),
        ),
    ),
)

runner = NeutralRunner(actions)
instance = runner.start(workflow, TenantScope(tenant_id="acme", case_ref="c-1"))
instance = runner.run(instance)
assert instance.status.value == "paused_approval"  # waiting for a human

from datetime import datetime, timezone
from seasi_core.contracts.evidence import ApprovalDecision


def approver(intent):  # in production this is your reviewer UI
    return ApprovalDecision(
        intent_id=intent.intent_id,
        approved=True,
        decided_by="reviewer@acme",
        decided_at=datetime.now(timezone.utc),
    )


instance = runner.run(instance, approver=approver)
assert instance.status.value == "completed"
```

## Module ecosystem (separate private repositories)

SEASI-CORE is deliberately a **kernel, not a product**. Product lines are
private modules that register capabilities and workflows:

| Module | Scope |
|---|---|
| **GESTIÓN AUTÓNOMA** | Autonomous-client management: onboarding, census, filings, follow-ups. |
| **CONTA-LABORAL** | Accounting + payroll: document intake, ledgers, tax forms, payroll runs. |
| **MARKETING** | Campaigns, content pipelines, social publishing with approval gates. |

Each module ships a `ModuleManifest` (id, version, capabilities, workflows)
and is validated against the kernel registries at load time. Gestorías grow
the platform by expressing needs as **new capabilities in a module — never
by forking the kernel**. Tenant-specific branding, roles and parameters are
configuration (tenant packs), not code.

## Repository layout

```text
src/seasi_core/
├── contracts/       # tenant, capabilities, events, evidence, workflows
├── kernel/          # fail-closed context, registries, effect policy, intent binding
├── orchestration/   # neutral runner with HITL approval gates
├── sdk/             # Module SDK: contract product modules implement
└── observability/   # structured logging (tenant/workflow/case/state)
schemas/v1/          # closed JSON Schema twins of the core contracts
tests/               # unit · contract · isolation · integration
docs/                # ADRs and architecture decisions
```

## Status

`v0.2.3` — kernel contracts, declarative data binding (`ActionCall.input_from`), neutral runner with HITL approval authority
(one approval per call, reentrancy guard, explicit intent expiry), and the
Module SDK (`seasi_core.sdk`) that product modules implement to register
capabilities and workflows against the kernel.
See [ROADMAP.md](ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md).

## License

Source available for review and CI transparency — **not** open source for
commercial use. See [LICENSE](LICENSE).
