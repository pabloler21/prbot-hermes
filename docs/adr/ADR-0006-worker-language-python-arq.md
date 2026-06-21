# ADR-0006 — Reemplazo de BullMQ/TypeScript por arq/Python

- **Estado:** aceptado (reemplaza a ADR-0005)
- **Fase:** 3b
- **Fecha:** 2026-06-21

## Contexto

ADR-0005 eligió TypeScript + BullMQ optimizando un criterio: "cuál es la mejor
herramienta técnica para una cola durable". Ese criterio estaba **incompleto**.

Este repositorio es un **proyecto de portfolio** que el autor debe poder **explicar
y defender en entrevistas**, y su stack es **Python**, no TypeScript. Un componente
central escrito en un lenguaje que el autor no domina no cumple la función del
proyecto: al contrario, juega en contra. Además, el VPS es **Oracle Always Free
(1GB de RAM, sin presupuesto)**, así que el consumo de recursos es una restricción
dura.

Con esos dos criterios sobre la mesa (defendibilidad en el stack del autor +
costo/recursos), la decisión cambia.

## Decisión

**La capa de colas/workers se escribe en Python con la librería `arq`.**

`arq` es una cola de tareas basada en asyncio + Redis. Se elige sobre las
alternativas Python (Celery, RQ, Dramatiq) por encajar con las restricciones.

## Evidencia (verificada, 2026-06-21)

Footprint (web; ver Judoscale y comparativas low-resource):
- **RQ:** hasta ~2.1 GB por worker en picos, hace forking. Inviable en 1GB.
- **Celery:** ~340 MB, modelo prefork + necesita Celery Beat como proceso aparte
  para scheduling. Pesado para 1GB con Hermes y Redis ya corriendo.
- **arq:** async, sin forking, footprint mínimo. Pensado para entornos con pocos
  recursos e I/O-bound (nuestro caso: llamadas a la API de GitHub).

Capacidades de arq (verificadas vía Context7, doc oficial arq-docs.helpmanual.io):
- **Idempotencia / uniqueness:** `enqueue_job(..., _job_id=...)`; si el id ya existe
  encolado/corriendo, devuelve `None`. Más simple que BullMQ.
- **Retries con backoff:** `raise Retry(defer=ctx['job_try'] * 5)`; tras `max_tries`
  (default 5) el job falla permanentemente.
- **Cron / scheduling:** `cron(func, hour={...}, minute=...)` en `WorkerSettings.cron_jobs`.
  Esto es justo lo que el port de Python de BullMQ NO tenía (ver ADR-0005).
- **Jobs diferidos:** `_defer_by` / `_defer_until`.
- **Redis-nativo:** reusa el Redis ya instalado y asegurado en el VPS; sin brokers nuevos.

Salvedad registrada: arq está en "maintenance-only mode" (sin features nuevas, pero
mantenido y estable). Aceptable para una cola de tareas, que es una necesidad madura.

## Alternativas consideradas

1. **BullMQ + TypeScript (ADR-0005).** Técnicamente sólido, pero no defendible en el
   stack del autor. Descartado por el criterio correcto.
2. **BullMQ Python.** Le faltan schedulers/retries/events (ver ADR-0005). Descartado.
3. **Celery.** Muy defendible y activo, pero pesado para 1GB (worker + Beat). Sería la
   elección si la prioridad fuera "nombre conocido + desarrollo activo" sobre recursos.
4. **RQ / Dramatiq.** RQ consume demasiada RAM; Dramatiq viable pero sin ventaja clara
   sobre arq para async I/O-bound.
5. **arq.** Elegido.

## Consecuencias

- Se elimina todo el andamiaje TypeScript (`queue/` en TS, `package.json`, `tsconfig`,
  `node_modules`). El repo vuelve a ser homogéneo en Python (uv + Ruff).
- **El paquete Python se llama `hermes_queue/`, no `queue/`**: `queue` es un módulo de
  la librería estándar de Python y nombrar así un paquete top-level lo "taparía",
  rompiendo dependencias que hagan `import queue`. Se actualiza la estructura del repo.
- El approval gate (Enfoque B) se mapea a arq así: la **sala de espera** es una clave
  de Redis (`pending-approval:<id>`), no una cola de arq; la **cola de ejecución** es la
  de arq, que el worker consume. Solo lo aprobado se encola en la cola de arq.
- Hay que agregar `arq` como dependencia (`uv add arq`). El worker correrá como servicio
  systemd en el VPS (paso de deploy posterior).

## Nota de proceso

Es la segunda corrección de fundamento en esta decisión (ADR-0005 ya había corregido un
prejuicio sobre el port de Python). La lección queda registrada: definir el criterio
correcto ANTES de evaluar opciones. Acá el criterio que mandaba —defendibilidad en el
stack del autor + restricción de recursos— no se había hecho explícito al inicio.
