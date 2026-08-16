# Arquitectura del kernel

```text
┌────────────────────────────────────────────────────────────────┐
│ Harness de agentes (externo, neutral)                          │
│ sesión · eventos · aprobaciones · handoff humano               │
└───────────────┬────────────────────────────────────────────────┘
                │ contratos versionados (seasi.*/v1)
┌───────────────▼────────────────────────────────────────────────┐
│ SEASI-CORE                                                     │
│                                                                │
│  contracts          kernel                 orchestration       │
│  ───────────        ───────────────         ──────────────      │
│  TenantScope        context (CV)            NeutralRunner      │
│  CapabilitySpec     registries              WorkflowInstance   │
│  EffectClass        EffectPolicy            approval gates     │
│  ApprovalIntent     intent_binding          EventSink          │
│  WorkflowDef        ModuleManifest                             │
│  EventEnvelope                             observability       │
│                                            ────────────        │
│                                            structured logs     │
└──────┬───────────────┬───────────────┬─────────────────────────┘
       │               │               │
  GESTIÓN         CONTA-          MARKETING          (módulos
  AUTÓNOMA        LABORAL                            privados,
  (privado)       (privado)                          repos propios)
       │               │               │
  sistemas de registro externos (contable, AEAT, bancos, social)
```

## Flujo de un efecto gobernado

```text
start(workflow, TenantScope)          # fail-closed: tenant obligatorio
  ↓
transición declarativa
  ↓
CapabilitySpec del ActionRegistry     # desconocida → error al arrancar
  ↓
EffectPolicy.allows(effect)
  ├─ read / local_draft → handler inline (opcional) → evento
  └─ external_mutation
       ↓
     ApprovalIntent sellado (SHA-256 del payload exacto, TTL, nonce)
     estado = paused_approval → evento approval.requested
       ↓ humano revisa EXACTAMENTE ese digest
     ApprovalDecision → verify_intent (tenant+capability+payload+expiración)
       ├─ inválido → approval.invalid (sigue pausado, nunca ejecuta)
       ├─ rechazado → approval.rejected → workflow.failed (auditable)
       └─ válido → approval.granted → handler → evento con digest
```

## Invariantes del kernel

1. **Sin tenant por defecto** — `TenantContextError` si falta scope.
2. **Sin doble registro** — los registries son append-only y fallan cerrado.
3. **Sin efecto externo sin aprobación verificada** — el digest sella el
   payload exacto; alterarlo invalida la aprobación.
4. **Sin workflows con capabilities fantasma** — validación al `start`.
5. **Eventos tipados y digeridos** — cada evento lleva tenant,
   correlación/causación y SHA-256 del payload.
6. **Determinismo** — transiciones en orden de declaración, reloj
   inyectable, checksums canónicos.
