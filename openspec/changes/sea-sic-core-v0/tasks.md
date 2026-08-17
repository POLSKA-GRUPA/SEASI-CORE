# Tasks — sea-sic-core-v0

## 1. Contratos y SSOT
- [ ] 1.1 Definir `schemas/v1/session.schema.json` (id, tenant, cliente, trimestre, estado, adaptador)
- [ ] 1.2 Definir `schemas/v1/hitl-pause.schema.json` (efecto, digest, artefacto, estado pausa)
- [ ] 1.3 Definir `schemas/v1/artifact.schema.json` (tipo, hash, path, provenance)
- [ ] 1.4 Definir `schemas/v1/shell-api.schema.json` (métodos JSON-RPC del shell)
- [ ] 1.5 Pipeline de generación: JSON Schema → Zod (TS) + Pydantic (Py) con checksum en CI (drift imposible)

## 2. Kernel (SEASI-CORE, aditivo)
- [ ] 2.1 Puerto `HarnessAdapter` versionado + registro de adaptadores
- [ ] 2.2 Adaptador `pi` headless (spawn, stream de eventos, steering, presupuesto)
- [ ] 2.3 Endpoint JSON-RPC sobre stdio/socket local con validación fail-closed
- [ ] 2.4 Ledger append-only SQLite con hash encadenado + checkpoints idempotentes (reanudar tras cierre)
- [ ] 2.5 HITL persistido: pausa serializada + `ApprovalIntent` firmado (reusar schemas/v1)
- [ ] 2.6 Scope de tenant por código: partial application de rutas/efectos por inquilino
- [ ] 2.7 Tests de aislamiento entre tenants y de fail-closed sin tenant

## 3. Shell (seasi-despacho, Electron + TS strict)
- [ ] 3.1 Bootstrap electron-vite + TS strict + ESLint + Vitest; domains por screaming architecture
- [ ] 3.2 Preload mínimo: contextBridge `seasi` con IPC namespaced (`seasi:session:*`, `seasi:hitl:*`, `seasi:vault:*`); sandbox ON, contextIsolation ON, nav guards + whitelist openExternal
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
