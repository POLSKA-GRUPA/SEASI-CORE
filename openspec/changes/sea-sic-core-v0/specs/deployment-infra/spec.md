# Spec Delta — sea-sic-core-v0 / deployment-infra

## ADDED Requirements

### Requirement: Fase interna con coste cero
La v0 se desplegará en el cliente cero sin coste de infraestructura: DMG con firma ad-hoc + `install.sh` documentado (incluye el paso Gatekeeper explícito), y feed de actualizaciones en GitHub Releases privado.

#### Scenario: instalación interna
- **WHEN** un equipo del despacho instala la v0 en su Mac
- **THEN** el script guía la excepción de Gatekeeper conscientemente y verifica el checksum del DMG

#### Scenario: actualización interna
- **WHEN** la app consulta el feed privado
- **THEN** valida la firma del manifest (clave pública embebida) y rechaza paquetes sin firma o con versión inferior

### Requirement: Integridad de actualizaciones firmadas
Todo paquete de actualización incluirá manifest firmado (ed25519) con versión, checksum y canal. La app embeberá la clave pública y verificará antes de instalar. Downgrades y paquetes inválidos se rechazan sin intervención.

#### Scenario: servidor comprometido
- **WHEN** un atacante sustituye un paquete en el canal
- **THEN** la verificación de firma falla y la app no instala nada

### Requirement: Prohibición de telemetría con datos de cliente
El shell no enviará telemetría remota que contenga datos de clientes del despacho. El soporte se hará con paquetes de diagnóstico exportados localmente por el usuario.

#### Scenario: GDPR del despacho
- **WHEN** se abre un ticket de soporte
- **THEN** el usuario exporta el paquete de diagnóstico y decide qué enviar; el sistema no envía nada por sí solo

### Requirement: Backups locales automáticos
El estado (SQLite ledger + brain/ + config de inquilino) se exportará automáticamente a la carpeta de respaldo del despacho con retención configurable y restauración verificada.

#### Scenario: disco corrupto
- **WHEN** se pierde la base local
- **THEN** la restauración desde el último backup reconstruye ledger y brain íntegros (verificación de hash)

### Requirement: Gate comercial explícito
Ningún inquilino externo se desplegará hasta completar la fase comercial: Apple Developer Program (Developer ID + notarización stapled), firma Windows (Azure Trusted Signing o equivalente), y CI matrix (macOS arm64 + Windows x64) que compile, firme, notarice y publique por canal de inquilino.

#### Scenario: primer cliente externo
- **WHEN** se prepara el despliegue del segundo despacho (pagando)
- **THEN** el checklist comercial está en verde: DMG firmado y notarizado, instalador Windows firmado, canal dedicado con entitlement firmado

#### Scenario: CI como fábrica
- **WHEN** se publica una release
- **THEN** el pipeline ejecuta lint → tests (incluida paridad) → build 2 plataformas → firma → notarización → publicación a los canales, sin pasos manuales

### Requirement: Aislamiento de canales por inquilino
Cada inquilino recibirá updates solo de SU canal. El entitlement firmado del paquete debe coincidir con el tenant configurado en la instalación.

#### Scenario: paquete cruzado
- **WHEN** un paquete del canal del despacho A llega a una instalación B
- **THEN** la instalación B lo rechaza por mismatch de entitlement
