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
- [x] 3.1 Bootstrap electron-vite + TS strict + ESLint + Vitest; domains por screaming architecture (repo `~/SEASI-DESPACHO`)
- [x] 3.2 Preload mínimo: contextBridge `seasi` con IPC único (`seasi:rpc`); sandbox ON, contextIsolation ON, nav guards + CSP (ESLint pendiente de añadir al instalar deps)
- [ ] 3.3 Rail de despacho: clientes (NIF) → carpeta de Drive → sesión por trimestre
- [ ] 3.4 Vista de sesión: chat estructurado + terminal PTY de solo-log
- [ ] 3.5 Cola HITL: tarjetas de aprobación con artefacto + digest; aprobar/rechazar emite ApprovalIntent
- [ ] 3.6 Vault: safeStorage + inyección por env; gestión de credenciales del despacho (IMAP, Drive, AEAT, modelos)
- [ ] 3.7 Proxy local MCP para OAuth (patrón google-rest-mcp auditado): tokens solo en env del proxy
- [ ] 3.8 Brain: plantilla `brain/` con wikilinks por despacho/cliente + vista grafo + board kanban (parser roadmap.md)
- [ ] 3.9 Panel de diagnóstico: exportar paquete local (traces anonimizadas + replay)
- [ ] 3.10 Dashboard de uso por sesión/modelo
- [ ] 3.11 Loader white-label: `tenant/<id>/config.yaml` firmada (3 planos: marca/capacidades/gobierno)

## 4. Despliegue
- [ ] 4.1 FASE INTERNA: build DMG ad-hoc + `install.sh` (Gatekeeper consciente + checksum)
- [ ] 4.2 Feed updates GitHub Releases privado + manifest firmado ed25519 + clave pública embebida + anti-downgrade
- [ ] 4.3 Backups locales automáticos (SQLite + brain + config) con restauración verificada
- [ ] 4.4 GATE COMERCIAL (checklist): Apple Developer ID + notarización · Azure Trusted Signing · CI matrix mac/win → firma → notariza → publica por canal · entitlement por inquilino · rechazo de paquetes cruzados

## 5. Calidad
- [ ] 5.1 Harness de paridad: mismos tests JSON-RPC contra pi (y futuro ASIN)
- [ ] 5.2 Tests UI: Testing Library + Vitest sobre comportamientos (marca aplicada, HITL flujo, IPC)
- [ ] 5.3 Auditoría automática de superficie IPC en CI (diff de canales expuestos)
- [ ] 5.4 Plan de replay: reproducir sesión completa desde ledger en tests e2e
