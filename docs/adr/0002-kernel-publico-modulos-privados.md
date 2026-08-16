# ADR-0002: Kernel público source-available, módulos privados

- **Estado:** Aceptado
- **Fecha:** 2026-08-16
- **Decisores:** Kenyi Martín Alcántara (CTO/fundador)

## Contexto

SEASI se comercializa como plataforma para gestorías. Se requiere:

- GitHub Actions funcionando sin fricción (repos públicos: minutos libres);
- credibilidad técnica (kernel auditable por clientes y partners);
- protección del valor comercial (módulos de producto y know-how).

## Decisión

1. **Este repositorio (kernel) es público source-available**: visible,
   auditable, forkeable solo para proponer cambios; SIN licencia de uso
   comercial (ver LICENSE). En el futuro puede adoptarse BUSL-1.1 u otra
   licencia source-available estándar por decisión del titular.
2. **Los módulos de producto son repos privados**: GESTIÓN AUTÓNOMA,
   CONTA-LABORAL, MARKETING. Ningún código comercial vive aquí.
3. **Este repositorio no contiene datos de clientes, credenciales, prompts
   propietarios ni literales de marca heredada** — enforced por el job de
   higiene de CI (`pgk|polska|hiszpania` → fallo).
4. El historial arrancó de cero (huérfano) el 2026-08-16 para garantizar
   cero rastros; el historial del precursor se conserva como bundle firmado
   (SHA-256) fuera del repositorio.

## Alternativas descartadas

- *Kernel privado*: pierde Actions libres y credibilidad de auditabilidad.
- *Todo en un monorepo público*: regalaría el producto.
- *Kernel open source (MIT/Apache)*: permitiría uso comercial sin
  compensación; se reevaluará si se busca adopción comunitaria.

## Consecuencias

- La marca del kernel es nueva desde el día uno.
- La transferencia futura a otra organización propietaria es un simple
  `gh repo transfer` con redirección automática.
- Los clientes pueden auditar exactamente qué gobierna sus workflows.
