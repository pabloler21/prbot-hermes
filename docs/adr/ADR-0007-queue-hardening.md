# ADR-0007 — Endurecimiento de la cola: dead-letter y rate-limiting

- **Estado:** aceptado
- **Fase:** 4
- **Fecha:** 2026-06-23

## Contexto

La Fase 4 del plan ("infra de cola durable como servicio de producción") pide
reintentos con backoff, **dead-letter**, **rate limiting**, supervivencia a reboot y
observabilidad. Buena parte ya se entregó en la Fase 3b (Redis asegurado, worker y bot
como servicios systemd, reintentos con backoff exponencial). Quedaban dos piezas que arq
**no resuelve de forma nativa** y había que decidir cómo implementarlas.

Verificado vía Context7 (doc oficial arq-docs.helpmanual.io, 2026-06-23):
- arq **no tiene dead-letter queue**: cuando un job supera `max_tries`, arq lo marca
  como fallido (`JobExecutionFailed('max N retries exceeded')`) y guarda el resultado,
  pero **el payload no queda en ninguna cola revisable** — se pierde.
- arq **no tiene rate-limiter por QPS** (token-bucket). Su único control de caudal es
  `max_jobs` (concurrencia, default 10) y `poll_delay` (default 0.5s).

## Decisión

**1. Dead-letter por lista de Redis (`hermes_queue/deadletter.py`).**
- Clave `dead-letter:post_comment`, una lista de Redis.
- `record_dead_letter()` hace `LPUSH` del payload + motivo + timestamp, y `LTRIM` a las
  últimas 100 entradas (cap de memoria — importa en 1GB).
- `list_dead_letters()` para inspeccionar; `requeue_dead_letter()` para reintento manual.
- El worker manda al DLQ **tanto** los fallos permanentes (4xx de GitHub, repo fuera de
  la allowlist) **como** los transitorios que agotan los 5 reintentos. Antes, los fallos
  permanentes hacían `return None` y se perdían sin rastro.

**2. Rate-limiting = cap de concurrencia (`max_jobs = 2`).**
- No implementamos token-bucket por QPS: la arquitectura no lo necesita hoy. El
  **approval gate humano** ya es el throttle real de las escrituras (una persona aprueba
  de a un pedido por vez). `max_jobs = 2` es defensa en profundidad contra que el agente
  24/7, en algún escenario de reintentos, haga burst contra la API de GitHub.

## Alternativas consideradas

- **Dead-letter vía `on_job_end`/inspección de resultados fallidos de arq.** Más
  acoplado a internals de arq y más difícil de leer/reintentar. La lista de Redis es
  explícita, inspeccionable con `redis-cli` y trivial de reencolar. Elegida.
- **Token-bucket QPS real (p. ej. con una lib de rate-limiting o LUA en Redis).** YAGNI
  para escrituras con gate humano. Se reevaluará en Fase 5/6, cuando aparezcan workers de
  *poll* que sí generan caudal automático contra GitHub/LLM.
- **Métricas Prometheus / dashboards.** Sobredimensionado para 1GB y para el alcance del
  demo. La observabilidad se cubre con el health-check nativo de arq (`arq --check`) y un
  runbook (`docs/runbook.md`).

## Consecuencias

- Nuevo módulo `hermes_queue/deadletter.py` y wiring en el worker.
- `WorkerSettings` fija `max_tries = 5` (explícito) y `max_jobs = 2`.
- `requeue_dead_letter()` reencola **sin `_job_id`** a propósito: es un reintento manual
  deliberado, así que la idempotencia no debe descartarlo por chocar con un resultado
  viejo en caché. Reencolar es seguro porque el DLQ solo contiene trabajo ya aprobado.
- Runbook ampliado con operación de la cola (ver largo, listar/reintentar DLQ, health).
- La supervivencia a reboot de los servicios nuevos (`hermes-arq-worker`,
  `hermes-approval-bot`) se valida como PASO MANUAL en el VPS.
