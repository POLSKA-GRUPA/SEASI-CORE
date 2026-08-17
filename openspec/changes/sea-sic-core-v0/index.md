# Index — sea-sic-core-v0

| Documento | Estado | Propósito |
|---|---|---|
| [proposal.md](proposal.md) | listo | Motivación, alcance, impacto, no-objetivos |
| [design.md](design.md) | listo | Arquitectura, patrones adoptados (auditoría Granular + Orca/Conductor/cmux), seguridad, 2 fases de despliegue |
| [specs/despacho-shell/spec.md](specs/despacho-shell/spec.md) | listo | 10 requisitos con escenarios (RPC, runtime-agnostic, SSOT, HITL, ledger, vault, scope, brain, white-label, CLI) |
| [specs/deployment-infra/spec.md](specs/deployment-infra/spec.md) | listo | 7 requisitos de infra (fase interna 0€, updates firmados, no-telemetría, backups, gate comercial, canales) |
| [tasks.md](tasks.md) | listo | 5 bloques / 28 tareas en orden de ejecución |

## Trazabilidad de evidencia

- **Auditoría DMG Granular v0.3.80** (forense completa, 2026-08-17): patrones vault/env-injection, mcp-auth-proxy, IPC `granular:*`, brain .md+board, skills manifest — orígenes de los patrones en design.md §2. Engram: obs #8462, #8464, #8466, #8468.
- **Ecosistema**: Orca (worktrees por agente, CLI paridad --json, jump palette), Conductor (setup scripts, puerto por workspace, flujo PR), cmux/kmux (dashboard uso, worktree por sesión), Codex App (diff review nativo).
- **Cuadernos NotebookLM**: Gentleman Programming (Electron/YAGNI/TDD), Código Espinoza (tipado estático + IA, híbrido Python+Rust diferido), Infraestructura Operativa (5 blindajes), Ingeniería IA (JSON-RPC no PTY, SSOT, HITL persistido, paridad).

## Gate de archivo

El change se archiva cuando: specs ✓, tasks 1-4.3 ✓ (interno desplegado en el despacho), paridad ✓, y el bloque 4.4 queda registrado como gate abierto para la fase comercial.
