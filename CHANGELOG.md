# Changelog

Todos los cambios notables del kernel se documentan aquí.
Formato basado en Keep a Changelog; versionado SemVer.

## [0.2.0] — 2026-08-16

### Added
- **Module SDK** (`seasi_core.sdk`): `ModuleBuilder`, `LoadedModule`,
  `install_module` — handshake fail-closed entre módulos de producto y el
  kernel: duplicados rechazados, workflows solo pueden usar capabilities
  propias del módulo (composición cruzada explícita, nunca implícita),
  manifest coherente con lo entregado.
- `WorkflowRegistry` con acceso a checksums de definiciones instaladas.
- Tests SDK (builder, handshake, end-to-end con gate HITL desde un módulo).

## [0.1.0] — 2026-08-16

### Added
- Contratos núcleo: `TenantScope`, `CapabilitySpec` (clases de efecto
  `READ`/`LOCAL_DRAFT`/`EXTERNAL_MUTATION`), `EventEnvelope`,
  `EvidenceRef`, `ApprovalIntent`/`ApprovalDecision`,
  `WorkflowDefinition` con checksum determinista.
- Kernel fail-closed: contexto de tenant obligatorio (`ContextVar` sin
  default), `Registry`/`ActionRegistry`/`ModuleRegistry` append-only,
  `EffectPolicy` (mutaciones requieren aprobación verificada),
  `intent_binding` (digest canónico JSON, verificación de tenant +
  capability + payload + expiración).
- Orquestación: `NeutralRunner` determinista con gates HITL: pausa
  `paused_approval`, reanudación con verificación, rechazo auditable,
  presupuesto de pasos, idempotencia en estados finales.
- Observabilidad: logging estructurado JSON con `tenant_id`, `workflow_id`,
  `case_id`, `state` obligatorios.
- Schemas JSON v1 (tenant-scope, approval-intent, event-envelope) cerrados
  (`additionalProperties: false`).
- Suites de tests: unit, contract, isolation (multi-tenant), integration
  (flujo HITL completo, payload alterado, rechazo, replay).
- CI: ruff format/check, mypy, pytest matrix 3.11–3.13, job de higiene
  anti-literales heredados.
- Fundación del repositorio: arranque limpio el 2026-08-16 (historial
  previo del precursor preservado fuera del repo por decisión fundacional).
