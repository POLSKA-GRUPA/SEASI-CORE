# ROADMAP — SEASI platform

> Principio rector: **el kernel es público y auditabile; el valor comercial
> vive en módulos privados**. Cada necesidad de una gestoría se materializa
> como una capability nueva en un módulo — jamás como un fork del kernel.

## v0.1.0 — Kernel (este repositorio) ✅

- Contratos núcleo: `TenantScope`, `CapabilitySpec`, `EffectPolicy`,
  `ApprovalIntent`, `WorkflowDefinition`, `EventEnvelope`.
- Runner neutral determinista con gates HITL por digest exacto.
- Fail-closed: sin tenant implícito, sin efectos externos sin aprobación
  verificada, sin capacidades desconocidas.
- Aislamiento probado entre tenants (tests de isolation).
- CI: lint + format + mypy + pytest (3.11/3.12/3.13) + higiene anti-literales.

## v0.2 — Module SDK + GESTIÓN AUTÓNOMA (repo privado)

- SDK de módulo: `ModuleManifest`, loader, validación de handshake contra
  registries del kernel, plantilla de repo de módulo con CI propia.
- Primer módulo producto: **GESTIÓN AUTÓNOMA** (alta de autónomos,
  expediente censal, seguimiento de obligaciones, recordatorios HITL).
- Capability catalog inicial: `census.read`, `filing.draft`,
  `filing.submit` (external_mutation, gated).

## v0.3 — CONTA-LABORAL (repo privado)

- **CONTA-LABORAL**: ingesta documental con extracción asistida, libro de
  facturas propuesto, nóminas, modelos tributarios.
- Bridge al sistema contable externo vía puerto read/post con aprobación;
  el sistema externo es el system-of-record contable.
- Contratos documentales v2 (partidas, rectificativas, retenciones).

## v0.4 — MARKETING (repo privado)

- **MARKETING**: campañas, contenido, programación social con cadence y
  aprobaciones de un solo uso.
- Publicación = external_mutation gated; borradores = local_draft.
- Métricas de campaña como capabilities de solo lectura.

## v0.5 — Harness adapters

- Adaptador de contrato versionado para arneses de agentes
  (sesión, eventos, aprobaciones, handoff humano).
- Mismo workflow ejecutado desde runner neutral y desde arnés externo:
  paridad de eventos.

## v0.6 — Tenant packs

- Packs de configuración por gestoría (branding, roles, idiomas, SLA,
  plantillas) sin tocar código.
- Prueba de aceptación: dar de alta un tenant nuevo = solo configuración.

## Principios no negociables

1. Sin tenant por defecto (fail-closed en todas las capas).
2. Toda mutación externa requiere `ApprovalIntent` verificada.
3. El kernel nunca importa módulos; los módulos dependen del kernel.
4. Los sistemas de registro externos conservan la autoridad de sus datos.
5. Cero literales de marca heredada (enforced por CI).
6. Historia y procedencia preservadas; este repo arrancó de cero por
   decisión fundacional (2026-08-16).
