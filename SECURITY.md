# Security Policy

## Reporte de vulnerabilidades

No abras issues públicos para vulnerabilidades. Contacta directamente al
mantenedor por el canal privado indicado en el perfil de la organización.

## Modelo de amenazas del kernel (resumen)

- Aislamiento multi-tenant por contrato: sin `tenant_id` no hay operación
  (fail-closed). El kernel no mantiene estado compartido entre tenants.
- Efectos externos: solo tras `ApprovalIntent` verificada (digest exacto,
  TTL, nonce). El kernel jamás ejecuta I/O de red por sí mismo.
- Integridad: digests SHA-256 canónicos en intents y eventos.
- El job de higiene de CI bloquea literales de marca heredada y cualquier
  contenido que no pertenezca a este proyecto.

## Alcance

El kernel es una librería; el despliegue seguro (transporte, secretos,
perfiles de red) es responsabilidad de los módulos y del tenant pack.
