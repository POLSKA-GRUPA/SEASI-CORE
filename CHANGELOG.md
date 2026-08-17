# Changelog

Todos los cambios notables del kernel se documentan aquí.
Formato basado en Keep a Changelog; versionado SemVer.

## [0.2.3] — 2026-08-17

### Added
- **`ActionCall.input_from`**: binding declarativo de datos entre pasos.
  El runner resuelve rutas con puntos sobre `instance.data` ANTES de
  sellar el `ApprovalIntent`: el humano aprueba los valores reales.
  Fail-closed: ruta ausente → workflow FAILED, nunca dispatch parcial.
  Manipular los datos tras el sellado rompe la verificación (test).
- Tests de schema twins derivados de `model_json_schema()` + validación
  de instancias con jsonschema; los twins ya no derivan en silencio.

### Fixed
- Quickstart del README ejecutable de principio a fin (verificado).
- Twins corregidos: `required` sin campos con default; opcionales nullable.

## [0.2.2] — 2026-08-17

### Fixed
- **Guard de reentrancia**: `run()` sobre una instancia con otra ejecución
  activa lanza `WorkflowError` (contrato single-thread por instancia).
- Expiración de intent verificada con evento `approval.invalid` y test
  de regresión.

### Security
- Revisión adversarial (clones): sin dobles mutaciones externas por
  reentrada; cadencia HITL confirmada una-aprobación-por-llamada.

## [0.2.1] — 2026-08-17

### Fixed
- **Cadencia HITL**: `NeutralRunner.run(approver=...)` resuelve como máximo
  UNA aprobación por llamada y pausa en la siguiente puerta. Antes encadenaba
  todas las aprobaciones de golpe en una sola llamada, impidiendo revisar
  entre puertas. Cada llamada = exactamente un ciclo de decisión humana.

### Added
- Tests de regresión de cadencia (workflow con dos puertas).

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
