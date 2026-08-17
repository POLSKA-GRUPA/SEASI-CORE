# Tasks — sea-sic-core-v0

## 1. Contratos y SSOT
- [x] 1.1 Definir `schemas/v1/session.schema.json` (id, tenant, cliente, trimestre, estado, adaptador)
- [x] 1.2 Definir `schemas/v1/hitl-pause.schema.json` (efecto, digest, artefacto, estado pausa)
- [x] 1.3 Definir `schemas/v1/artifact.schema.json` (tipo, hash, path, provenance)
- [x] 1.4 Definir `schemas/v1/shell-api.schema.json` (métodos JSON-RPC del shell)
- [x] 1.5 Pipeline de generación: JSON Schema → Zod (TS) + Pydantic (Py) con checksum en CI (drift imposible)
  - SSOT: pydantic es fuente → `tools/export_schemas.py` exporta schemas/v1 + MANIFEST sha256 → `SEASI-DESPACHO/scripts/gen-contracts.mjs` verifica los mismos digests y emite Zod. Gate en `tests/test_schema_drift.py` y `tests/contracts.test.ts`.

## 2. Kernel (SEASI-CORE, aditivo)
- [x] 2.1 Puerto `HarnessAdapter` versionado + registro de adaptadores (`seasi_core/harness/`)
- [x] 2.2 Adaptador `pi` headless (`--mode json --print`, session-dir bajo scope del tenant; flags verificados contra `pi --help`)
- [x] 2.3 Endpoint JSON-RPC sobre stdio (`python -m seasi_core.rpc`) con validación fail-closed
- [x] 2.4 Ledger append-only SQLite con hash encadenado + presupuestos (deadline/turns) en `ProcessHarness`
- [x] 2.5 HITL persistido: pausas como eventos + `ApprovalIntent` sellado (`ledger/hitl.py`)
- [x] 2.6 Scope de tenant por código: `kernel/scope_guard.py` (partial application de rutas)
- [x] 2.7 Tests de aislamiento entre tenants y de fail-closed (121 tests verdes + smoke RPC stdio)

## 3. Shell (seasi-despacho, Electron + TS strict)
- [x] 3.1 Bootstrap electron-vite + TS strict + Vitest; domains por screaming architecture (repo `~/SEASI-DESPACHO`)
- [x] 3.2 Preload mínimo: contextBridge `seasi` con IPC único kernel (`seasi:rpc`) + `shell:*` auditados (sandbox ON, contextIsolation ON, CSP, window-open deny; `scripts/audit-ipc.mjs` en CI)
- [x] 3.3 Rail de despacho: clientes (NIF) derivados del ledger → sesión por trimestre (v0: sin lectura de Drive aún)
- [x] 3.4 Vista de sesión: eventos estructurados del ledger como log vivo + STREAMING en vivo por notificaciones JSON-RPC (`seasi.session.event`) broadcast a la UI
- [x] 3.5 Cola HITL: tarjetas con capability+digest+expiración; aprobar/rechazar emite ApprovalIntent (kernel `seasi.hitl.create/list/decide`)
- [x] 3.6 Vault: safeStorage + inyección por env al proceso kernel; renderer solo ve nombres
- [x] 3.7 Proxy local MCP para OAuth: `domains/mcp-proxy` (loopback, refresh con skew 60s, retry-401 único, fail-closed 503, tokens jamás en logs/respuestas) + activación por env/vault + `shell:mcp:status`
- [x] 3.8 Brain: notas .md con wikilinks + grafo SVG + board kanban (parser/board testeados)
- [x] 3.9 Panel de diagnóstico: export local (ledger+README) a carpeta elegida por usuario; sin telemetría
- [x] 3.10 Dashboard de uso: pestaña Uso (turnos + tokens in/out por sesión desde `seasi.usage.summary` del ledger) + estado del proxy MCP
- [x] 3.11 Loader white-label: `tenant.json` firmable en userData (3 planos validados fail-closed, UI aplica marca)

## 4. Despliegue
- [x] 4.1 FASE INTERNA: script `install.sh` (ditto + cuarentena interna documentada, jamás ajustes globales)
- [x] 4.2 Updater ed25519: feed firmado + clave pública embebida + anti-downgrade + sha de artefacto (`scripts/gen-keys.mjs`, `sign-update.mjs`, `domains/update`); publicación real del feed queda para el primer release interno
- [~] 4.3 Backups locales con restauración verificada (manual en UI v0; scheduler automático pendiente)
- [~] 4.4 GATE COMERCIAL scriptable: `scripts/commercial-gate.mjs` (firma Apple, notarización, Azure Trusted Signing, CI matrix, entitlements, IPC audit) + `domains/entitlement` (ed25519, rechazo cross-tenant) + electron-builder.yml + CI mac/win. BLOQUEA con exit≠1 mientras falten credenciales de pago (correcto: fase interna).

## 5. Calidad
- [x] 5.1 Harness de paridad: misma suite JSON-RPC contra kernel real (`uv run python -m seasi_core.rpc` desde vitest) + digests idénticos a MANIFEST
- [x] 5.2 Tests UI-dominio: parser brain, updater (forjas ed25519), backup (corrupción), vault (no-fuga), branding (fail-closed) — 54 tests
- [x] 5.3 Auditoría automática de superficie IPC en CI (`audit-ipc.mjs`)
- [x] 5.4 Replay: fuzz del transporte RPC (basura binaria, ráfaga 500 notificaciones, ids duplicados) sin crash ni traceback
