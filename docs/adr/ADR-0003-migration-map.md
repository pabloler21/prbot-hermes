# ADR-0003 — Mapa de migración de n8n a Hermes + BullMQ (Fase 2)

- **Estado:** confirmado
- **Fase:** 2
- **Fecha:** 2026-06-18

## Contexto

El sistema actual usa n8n para automatizaciones recurrentes sobre GitHub y Discord.
El objetivo es migrar esas automatizaciones a Hermes + BullMQ y retirar n8n.
Esta fase produce el inventario completo y las decisiones de migración por workflow,
que guían la implementación de las Fases 3–6.

## Decisiones

### 1. Criterio de clasificación: determinístico → BullMQ, criterio → Hermes

Workflows que ejecutan pasos predecibles (consultar API, formatear, postear) van a
BullMQ como jobs de workers. Tareas que requieren razonamiento sobre el código o el
contexto del proyecto van a Hermes como capacidad agéntica. Esta separación mantiene
el LLM fuera de la plomería recurrente, controlando costos y latencia.

### 2. Sin webhooks: se usa poll para alertas cuasi-tiempo-real

El PAT del equipo es de solo lectura (sin permisos de admin sobre repos), por lo que
no se puede registrar un webhook en GitHub. Los workflows de "nueva actividad"
(new issue, deploy notification) se implementan como jobs de BullMQ que pollan la API
cada 5 minutos. La latencia máxima de notificación es 5 min, aceptable para el caso de uso.

### 3. Idempotencia obligatoria desde el inicio

Los jobs de poll que corren cada 5 min, 24/7, en un sistema con reintentos, duplicarían
notificaciones sin idempotencia. Cada job que produce una notificación usa una clave
compuesta (`repo+identificador+timestamp`) para deduplicación en BullMQ.

### 4. Capacidad agéntica (PR Assistant) fuera del scope de migración

La capacidad de responder preguntas sobre PRs y debuggear CI en Discord no existe en
n8n y no es una migración sino una feature nueva. Se planifica para Fase 5, después de
que los guardrails de GitHub (allowlist, approval gate, PAT scopeado) estén probados.

### 5. Cutover en dos tiempos con criterio objetivo de 7 días

Se deshabilita n8n (reversible) solo cuando los 5 workflows equivalentes llevan 7 días
sin errores en producción. Se elimina n8n (irreversible) solo después del período de
observación. Los 7 días dan margen para detectar falsos negativos antes del punto de
no retorno.

## Workflows y su destino

| Workflow | Destino | Worker / Scheduler | Idempotencia |
|---|---|---|---|
| Daily PR Digest | BullMQ scheduler | `digest-daily` | `fecha+repos` |
| New Issue Alert | BullMQ scheduler (poll 5 min) | `issue-alert` | `repo+issue_number` |
| Stale PR Alert | BullMQ scheduler | `stale-pr-alert` | `fecha+repo` |
| Weekly Summary | BullMQ scheduler | `digest-weekly` | `semana+repos` |
| Deploy Notification | BullMQ scheduler (poll 5 min) | `deploy-notify` | `repo+pr_number+merged_at` |
| PR Assistant (nuevo) | Hermes agéntico | — (Fase 5) | N/A |

## Consecuencias

- Las Fases 3–6 tienen una tabla de referencia clara: qué construir, en qué orden y con
  qué criterios de idempotencia.
- El criterio de cutover es objetivo y verificable; no hay ambigüedad sobre cuándo se
  puede apagar n8n.
- El PR Assistant se desarrolla después de los guardrails, no antes, reduciendo el riesgo
  de acciones sin approval sobre repos reales.
