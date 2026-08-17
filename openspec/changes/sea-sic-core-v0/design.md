# Design — sea-sic-core-v0

## 1. Arquitectura

```text
┌─ seasi-despacho (Electron, TS strict, React) ─────────────┐
│ UI: rail de despacho · sesiones · HITL · brain · board    │
│    · vault · diffs · panel diagnóstico                    │
├───────────────────────────────────────────────────────────┤
│ Canal de NEGOCIO: JSON-RPC 2.0 sobre stdio/socket local   │
│   contratos generados desde schemas/v1 (Zod)              │
│ Canal VISUAL: node-pty → terminal de solo-log             │
├───────────────────────────────────────────────────────────┤
│ SEASI-CORE (kernel Python): tenancy · contracts · HITL    │
│   runner neutro · events · evidence                       │
│   Puerto HarnessAdapter: [pi(TS) hoy] [ASIN(Py) mañana]  │
├───────────────────────────────────────────────────────────┤
│ Módulos privados: GESTIÓN AUTÓNOMA · CONTA-LABORAL · …   │
│ Ledger append-only SQLite · Vault Keychain (env-inject)  │
└───────────────────────────────────────────────────────────┘
```

Decisiones (validadas contra los cuadernos NotebookLM del owner y la auditoría del DMG):

- **Electron + TS, no Tauri/Rust** (Gentleman Programming: YAGNI/KISS; con 1-2 devs Rust es sobreingeniería; el 10% crítico PTY ya existe como node-pty). Reevaluable en v2 si el target Windows tiene RAM crítica.
- **Un lenguaje por capa, dos en total**: TS en shell (igual que pi), Python ya en kernel. Prohibido un tercero.
- **JSON-RPC estructurado, PTY solo visual** (Ingeniería IA: parsear strings de terminal = complejidad accidental).
- **SSOT de contratos**: JSON Schema en `schemas/v1` → generación Zod + Pydantic. Deriva de contratos imposible por construcción.
- **HITL como interrupción persistida**: el estado de pausa se hidrata/deshidrata en SQLite; jamás `await input()` en memoria. Aprobación = evento firmado en el ledger (ya soportado por `ApprovalIntent` v1).
- **Stateless en RAM, stateful en disco**: append-only event log + checkpoints idempotentes (laptops que se duermen).
- **"Enforce, don't instruct"**: validadores post-generación fail-closed con JSON Schema antes de persistir o mostrar.

## 2. Patrones adoptados (auditoría DMG Granular v0.3.80 + ecosistema)

| Patrón | Origen verificado | Aplicación en SEASI |
|---|---|---|
| Vault = safeStorage (Keychain) + **inyección por env al proceso**, nunca al contexto del modelo | Granular `vaultEnv()` sobre PTYs | Vault del despacho: IMAP/Drive/AEAT claves por inquilino |
| MCP OAuth vía **proxies locales**: tokens solo en env del proxy, el agente habla con localhost | Granular `mcp-auth-proxy`, `google-rest-mcp` | Puente Google/Mail sin exponer refresh tokens |
| IPC namespaced por dominio (`granular:agent:*`) | Granular (~100 canales) | Canales `seasi:session:*`, `seasi:hitl:*`, `seasi:vault:*` |
| HITL por IPC events (`permission-decision`) | Granular | Aprobaciones con digest exacto del kernel |
| Skills = carpeta `manifest.json + RESOURCE.md + seed.prompt` | Granular library | Reutilizar formato skills de pi + registro del kernel |
| Brain = .md con wikilinks `[[X]]` + roadmap.md en board format | Granular project-brain | `brain/` por despacho y por cliente, vista grafo+kanban |
| **Worktree por sesión/agente** (no es sandbox de seguridad) | Orca, Conductor, cmux, Codex App | Aislamiento de efectos entre sesiones del mismo repo |
| Setup scripts + puerto por workspace | Conductor (`CONDUCTOR_PORT`) | Puertos/sesión para previews del despacho |
| Paridad CLI: todo lo de la UI también scripteable `--json` | Orca CLI | `seasi status --json` desde el día 1 (auditable, testeable) |
| Diff review + comentarios al agente en línea | Orca/Conductor | Revisión de artefactos (no solo código) |
| Dashboard de uso por sesión | cmux/kmux | Coste/modelo por sesión y por cliente |
| Update feed firmado: clave pública embebida + firma interna por paquete | cuaderno Infraestructura | Fase interna y comercial |

## 3. Seguridad del shell (requisitos duros)

- `contextIsolation: true`, `sandbox: true` en renderers, `nodeIntegration: false`; preload mínimo con `contextBridge` exponiendo SOLO el objeto `seasi` (auditar la superficie IPC en CI).
- `setWindowOpenHandler` + validación de `openExternal` con whitelist de dominios.
- Sin navegación web arbitraria dentro del shell.
- Rutas de inquilino congeladas por código (partial application en el kernel), no por prompt — defensa contra prompt injection por email (cuaderno Infraestructura).
- Botón "Exportar paquete de diagnóstico": traces anonimizadas + replay local. Telemetría remota: prohibida.

## 4. White-label: configuración en 3 planos

```yaml
# tenant/pgk.yaml (firmado)
brand:        { name, logo, icon, colors, email_domain }
capabilities: { modules: [gestion_autonoma, conta_laboral], skills: [...], connectors: [imap, drive, aeat] }
governance:   { hitl_required: [filing.submit, email.send], effect_policy: read-by-default, models_allowed: [...] }
```

Un inquilino nuevo = una carpeta + una firma. Cero forks del kernel o del shell. El gate de validación de config corre en el kernel (Zod/Pydantic generados, fail-closed).

## 5. Despliegue en dos fases (infraestructura como requisito)

**Fase INTERNA (v0 — el despacho, coste ≈ 0 €)**
- Build DMG con firma ad-hoc + script `install.sh` documentado (ajuste Gatekeeper explícito y consciente).
- Feed de actualizaciones: GitHub Releases **privado** + manifest firmado (ed25519); clave pública embebida en la app; downgrade y paquetes sin firma = rechazados.
- Windows: compila en CI pero se distribuye solo a el equipo interno (sin firma; documentado como interno).
- Backups: export local del SQLite + brain/ a la carpeta del despacho.

**Fase COMERCIAL (gate explícito)**
- Apple Developer Program (Developer ID + notarización stapled), firma Windows Azure Trusted Signing.
- CI matrix (mac arm64 + win x64): lint → tests → build → firma → notariza → publica al canal del inquilino.
- Canales por inquilino con entitlement firmado; N inquilinos sin N infiernos.
- Regla: **ningún inquilino externo antes de cruzar este gate** (está en specs/deployment-infra).

## 6. Testing

- TDD con specs primero (OpenSpec es la metodología del owner).
- **Harness de paridad**: el mismo set de tests JSON-RPC contra el adaptador pi y (futuro) ASIN; outputs e hitos HITL idénticos.
- Screaming architecture en el shell: `src/domains/{despacho,session,hitl,vault,brain,ledger,adapter,branding}/`.
- Prohibidos Pokémon handlers; fail-fast con Zod en cada frontera IPC/RPC.
