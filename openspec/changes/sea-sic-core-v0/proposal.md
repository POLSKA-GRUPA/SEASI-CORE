# Proposal: sea-sic-core-v0 — Despacho Shell v0 (cliente cero PGK) + despliegue en dos fases

## Motivación

SEASI-CORE ya es un kernel probado (v0.1 gates HITL, v0.2 GESTIÓN AUTÓNOMA, v0.3 CONTA-LABORAL) pero hoy solo es ejecutable vía código/CLI. Los usuarios de un despacho (asesores fiscales, no developers) no tienen superficie utilizable. Paralelamente, el análisis forense del producto Granular (granular.build v0.3.80) y el estudio del ecosistema (Orca, Conductor, Codex App, cmux/kmux) demuestran que un *shell* de escritorio sobre runtimes de agentes es viable por 1-2 devs en 6-8 semanas, y que los patrones necesarios (vault por env-injection, HITL por IPC, brain en markdown, worktrees por sesión) están validados en producción por terceros.

El objetivo: **SEASI Despacho**, la app de escritorio del despacho, construida primero para PGK (cliente cero) con coste de infraestructura ≈ 0 €, y lista para convertirse en producto white-label multi-inquilino cuando se pague la fase comercial (firma Apple/Windows, notarización, CI multiplataforma).

## ¿Qué cambia

1. **Nuevo artefacto `seasi-despacho/`** (Electron + TypeScript estricto + React): shell de escritorio local-first que habla **solo** con SEASI-CORE mediante JSON-RPC estructurado sobre stdio/socket local. PTY únicamente como canal visual de log, nunca como protocolo.
2. **Puerto de arnés (harness port) aditivo en el kernel**: contrato versionado `HarnessAdapter` que hoy implementa pi (headless/JSON) y que mañana implementará ASIN detrás del mismo contrato. El shell jamás depende de un runtime concreto.
3. **Contratos como fuente única de verdad**: extensión aditiva de `schemas/v1` (session, hitl-pause, artifact, shell-api) con generación dual **Zod (TS) + Pydantic (Python)** desde los mismos JSON Schema. Prohibido definir tipos a mano en dos lenguajes.
4. **White-label en 3 planos** (marca / capacidades / gobierno): cada inquilino es una carpeta de configuración firmada, no un fork.
5. **Despliegue en 2 fases** como requisitos de spec, no como después de pensar:
   - **Fase INTERNA (v0, PGK)**: DMG ad-hoc + script de instalación, GitHub Releases privado con feed de actualizaciones firmado (clave pública embebida), cero telemetría, coste 0 €.
   - **Fase COMERCIAL (gate)**: Developer ID + notarización Apple, firma Windows (Azure Trusted Signing), CI matrix mac/win, canales por inquilino. Ningún inquilino externo se despliega antes de cruzar este gate.

## Impacto

- **SEASI-CORE**: solo adiciones (puerto HarnessAdapter, schemas nuevos, endpoint JSON-RPC). Los contratos v0.1-v0.3 y módulos privados no se tocan.
- **Módulos (GESTIÓN AUTÓNOMA, CONTA-LABORAL, MARKETING)**: sin cambios; se consumen vía kernel.
- **ASIN**: sin cambios; hereda el contrato para su futura fase de adaptador.
- **PGK (cliente cero)**: pasa de flujos CLI/pi a la app del despacho con HITL visual.
- **Riesgo principal**: deriva de contratos entre TS y Python — mitigado por SSOT con generación de código y tests de paridad (mismo harness de tests contra pi y ASIN).

## No-objetivos (v0)

Marketplace público, Telegram/móvil, preview de webs, multiusuario en red, Rust/Tauri, telemetría remota, tienda pública de distribución.
