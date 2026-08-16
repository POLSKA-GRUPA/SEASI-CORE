# ADR-0001: Contratos versionados y autoridad HITL en el kernel

- **Estado:** Aceptado
- **Fecha:** 2026-08-16
- **Decisores:** Kenyi Martín Alcántara (CTO/fundador)

## Contexto

El kernel de SEASI debe orquestar workflows agénticos para gestorías con
requisitos de auditabilidad: ningún efecto externo sin revisión humana
acreditable, ningún dato sin tenant identificable, ningún contrato que
cambie silenciosamente.

## Decisión

1. **JSON (Pydantic v2 + JSON Schema) es contrato de intercambio**, no base
   de datos. Los sistemas de registro externos (contable, fiscal, bancario,
   social) conservan la autoridad de sus datos; el kernel emite comandos
   idempotentes y guarda referencias + evidencia.
2. **El HITL es una máquina de estados autorizada**, no un campo de texto.
   Un `ApprovalIntent` sella actor + tenant + capability + digest SHA-256
   del payload exacto, con expiración y nonce. Ejecutar algo distinto a lo
   aprobado es imposible por construcción (verificación fail-closed).
3. **Tenancy fail-closed**: sin `tenant_id` explícito no hay operación.
   No existen defaults ni fallbacks a ningún tenant.
4. **Contratos cerrados** (`extra="forbid"`, `additionalProperties: false`)
   y versionados; los schemas JSON publicados en `schemas/v1` son gemelos
   de los modelos Pydantic y se prueban contra ellos.
5. **Clases de efecto** declaradas por capability: `read`, `local_draft`,
   `external_mutation`. Solo la última requiere aprobación, y siempre.

## Alternativas descartadas

- *JSON como base de datos* (propuesta del precursor histórico): rechazada;
   pierde transaccionalidad, concurrencia, autorización y aislamiento.
- *Estado `VERIFICADO` autoafirmado en el payload*: rechazado; cualquier
   productor podría autodeclararse verificado.
- *Transformación "ciega" a formatos oficiales*: rechazada; los adaptadores
  de dominio validan y son responsables ante el sistema de registro.

## Consecuencias

- El kernel es pequeño y verificable; el valor de dominio vive en módulos.
- Todo consumidor externo depende de contratos versionados, no de internals.
- El historial del repositorio precursor se preserva fuera del repo
  (decisión de arranque limpio, 2026-08-16); sus principios vigentes
  (triangulación origen→procesamiento→consenso humano, evidencia con
  digest, separación presentación/dominio) quedan absorbidos aquí.
