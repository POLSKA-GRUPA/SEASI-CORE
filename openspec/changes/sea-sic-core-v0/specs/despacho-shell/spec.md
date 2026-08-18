# Spec Delta — sea-sic-core-v0 / despacho-shell

## ADDED Requirements

### Requirement: Canal de negocio estructurado
El shell se comunicará con SEASI-CORE exclusivamente mediante JSON-RPC 2.0 sobre stdio o socket local, con mensajes validados contra los JSON Schema de `schemas/v1`. El canal PTY será únicamente visual (log de solo lectura) y no se parseará para extraer estado de negocio.

#### Scenario: mensaje malformado
- **WHEN** el kernel recibe un mensaje RPC que no valida contra el schema
- **THEN** responde error tipado y NO ejecuta efecto alguno (fail-closed)

#### Scenario: canal visual
- **WHEN** una sesión está activa
- **THEN** el usuario ve un terminal de log en vivo cuyo contenido NO es fuente de estado para el shell

### Requirement: Runtime-agnosticismo del arnés
Todas las capacidades del despacho se consumirán a través del puerto `HarnessAdapter` versionado del kernel. El shell no contendrá referencias directas a pi, Claude Code, ni ASIN.

#### Scenario: cambio de runtime
- **WHEN** un inquilino cambia el adaptador de pi a ASIN manteniendo la versión de contrato
- **THEN** el shell funciona sin cambios de código ni re-release

#### Scenario: tests de paridad
- **WHEN** corre el harness de paridad en CI
- **THEN** el mismo set de inputs produce outputs y hitos HITL idénticos en todos los adaptadores registrados

### Requirement: Contratos con fuente única de verdad
Cada contrato nuevo (session, hitl-pause, artifact, shell-api) se definirá como JSON Schema en `schemas/v1` y generará validadores Zod (TS) y Pydantic (Python) automáticamente. Queda prohibido declarar tipos duplicados a mano en ambos lenguajes.

#### Scenario: drift imposible
- **WHEN** un PR modifica un contrato sin regenerar los validadores
- **THEN** el CI falla por checksum de código generado desactualizado

### Requirement: HITL como interrupción persistida
Todo efecto externo gated (filing.submit, email.send, mutation de sistema de registro) pausará el flujo con estado serializado en el ledger SQLite del kernel. La aprobación humana genera un `ApprovalIntent` firmado (digest exacto). Ninguna pausa vive solo en RAM.

#### Scenario: portátil que se duerme
- **WHEN** la app se cierra con un HITL pendiente y se reabre
- **THEN** la pausa se rehidrata desde el ledger y la tarea continúa sin duplicar efectos

#### Scenario: aprobación de modelo fiscal
- **WHEN** el agente termina un borrador de modelo AEAT
- **THEN** el shell muestra el artefacto, el digest y requiere aprobación humana explícita; sin ella no hay presentación (fail-closed)

### Requirement: Ledger append-only con evidencia
Cada acción de agente (input, tool, salida, decisión HITL, artefacto) se registrará como evento append-only en SQLite con timestamp, tenant, sesión y hash encadenado.

#### Scenario: auditoría
- **WHEN** un asesor pregunta "¿por qué se clasificó esta factura así?"
- **THEN** el replay del ledger reconstruye la secuencia completa con inputs y salidas

#### Scenario: paquete de diagnóstico
- **WHEN** el usuario pulsa "Exportar diagnóstico"
- **THEN** se genera un paquete local con traces anonimizadas y replay; ningún dato de cliente sale de la máquina

### Requirement: Vault del despacho con inyección por entorno
Las credenciales del inquilino (IMAP, Drive, AEAT, claves de modelo) se cifrarán con Keychain/DPAPI (safeStorage) y se inyectarán SOLO como variables de entorno a los procesos que las necesitan. Los secretos jamás entran al contexto del modelo ni a prompts.

#### Scenario: agente necesita el mail
- **WHEN** una skill requiere conexión IMAP
- **THEN** el proceso recibe la credencial por env; el modelo nunca ve su valor

#### Scenario: tokens OAuth
- **WHEN** se usa un conector OAuth (Gmail/Drive)
- **THEN** los refresh tokens viven solo en el vault y en el env de un proxy local; el agente habla con localhost

### Requirement: Sesiones aisladas por cliente
Cada sesión del despacho corresponderá a un cliente/trimestre con scope de tenant verificado por el kernel (TenantScope). El filesystem accesible por efecto queda acotado por código a la carpeta del inquilino (partial application), no por instrucción del prompt.

#### Scenario: aislamiento
- **WHEN** el agente de la sesión del cliente A intenta una ruta fuera de su scope
- **THEN** el kernel rechaza el efecto con error tipado, sin importar lo que diga el prompt

### Requirement: Brain del despacho
Cada despacho y cada cliente tendrá un `brain/` en markdown con wikilinks `[[X]]` (misión, decisiones, roadmap en board format). Los agentes leen y escriben el brain proactivamente; el shell lo renderiza como grafo y como tablero kanban.

#### Scenario: roadmap vivo
- **WHEN** un agente completa una tarea del roadmap
- **THEN** la tarjeta avanza de estado en el board sin intervención manual

### Requirement: White-label en tres planos
Un inquilino se definirá con una carpeta de configuración firmada con tres planos: marca, capacidades y gobierno. Instalar un inquilino nuevo no requerirá fork ni recompilación.

#### Scenario: segundo inquilino
- **WHEN** se da de alta un segundo despacho
- **THEN** se entrega carpeta de config + firma; el shell y el kernel no cambian

### Requirement: Paridad CLI
Toda operación de la UI tendrá equivalente CLI con salida `--json` auditable (`seasi status --json`, `seasi hitl list --json`).

#### Scenario: automatización del despacho
- **WHEN** el IT del despacho quiere automatizar un flujo
- **THEN** lo hace vía CLI/JSON sin depender de la UI
