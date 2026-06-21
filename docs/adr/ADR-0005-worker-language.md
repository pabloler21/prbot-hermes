# ADR-0005 — Lenguaje de los workers de BullMQ: TypeScript

- **Estado:** aceptado
- **Fase:** 3b (decisión que el plan ubicaba en Fase 4; se adelanta porque 3b ya
  necesita escribir el primer worker)
- **Fecha:** 2026-06-21

## Contexto

La capa de ejecución durable del proyecto es **BullMQ sobre Redis**. Hay que elegir
en qué lenguaje se escriben las colas y los workers. El plan dejó la decisión abierta
entre **TypeScript** (SDK de referencia, nativo de Node) y **Python** (homogéneo con
el tooling del repo: uv + Ruff). La estructura se mantuvo agnóstica hasta este punto.

BullMQ es originalmente una librería de Node.js. Existe un port oficial de Python
(mismo mantenedor, Taskforce.sh), y las colas son interoperables entre lenguajes
porque la lógica vive en scripts Lua dentro de Redis.

## Evidencia (verificada con Context7 + web, 2026-06-21)

Fuente primaria: repo oficial `/taskforcesh/bullmq` (`python/README.md`, doc gitbook).

La sección **"Features" del README de Python** declara que el port **NO** tiene
implementadas aún varias funciones que el de Node sí:
- **Repeatable jobs / job schedulers (cron)** — no implementado en Python.
- **Job retries** — listado como no implementado (matiz: el `add()` de Python acepta
  las opciones `attempts`/`backoff`, pero la lógica de reintento del worker figura
  como no portada; estado ambiguo y no confiable).
- **Job events** — no implementado en Python.
- **Job priority** — no implementado en Python.

Sí están en Python: encolar jobs, delayed jobs, deduplicación, workers, progress,
backoff (config), getters y FlowProducer (flows padre-hijo).

**Por qué decide:** las tres primeras (schedulers, retries, events) son justamente el
núcleo de lo que reemplaza a n8n en este proyecto: digests recurrentes (schedulers),
resiliencia del worker que publica en GitHub (retries) y reporte de resultados al canal
de Discord (events). En Node/TS son ciudadanas de primera clase y están documentadas;
en Python faltan o son dudosas.

Versiones verificadas (2026-06-21): BullMQ `5.79.0` (línea v5); `ioredis` viene incluido
como dependencia (no se instala aparte); Node.js LTS activo = **Node 24**; Redis 5.0+
requerido (el del VPS cumple).

## Decisión

**Toda la capa de colas/workers (`queue/`) se escribe en TypeScript sobre Node 24 LTS.**

## Alternativas consideradas

1. **Python (todo).** Descartado: faltan schedulers/retries/events, el núcleo del caso
   de uso. Apostar a features no portadas en la base del sistema es riesgo innecesario.
2. **Híbrido (producer Python + worker TS).** Descartado: fragmenta un subsistema
   cohesivo por una limitación de librería, no por una frontera de servicio real. Como
   lo que falta en Python es justo el worker (schedulers/retries/events), el "lado
   Python" se reduciría a `queue.add(...)`, sin justificar el costo de mantener dos
   toolchains, dos sets de dependencias, y un contrato de datos sincronizado a mano
   entre lenguajes sin tipos compartidos. Regla aplicada: **se divide por límites de
   servicio, no por disponibilidad de features.**
3. **TypeScript (todo).** Elegido.

## Consecuencias

- El repo queda **políglota a nivel macro pero limpio por frontera**: Python para su
  tooling/scripts; `queue/` 100% TypeScript, autocontenido. No es un híbrido forzado.
- Se incorpora un toolchain Node (npm, tsc, tsx) restringido a `queue/`. Hay que instalar
  Node 24 LTS en el VPS (paso manual) para correr los workers como servicio.
- Todo ejemplo/doc/StackOverflow de BullMQ matchea (ecosistema TS-first), lo que baja la
  fricción de desarrollo y mantenimiento.
- El tipado estático de TS aporta seguridad en el contrato de los jobs (forma del payload),
  relevante para idempotencia y para no postear basura en un PR real.

## Nota de proceso

Una primera evaluación en este proyecto recomendó TS con un fundamento equivocado
("Python es un port inmaduro de terceros" — falso: es oficial). Esta decisión corrige
el fundamento: la razón real y verificada es la falta de schedulers/retries/events en el
port Python, no su origen. Se documenta para no repetir el prejuicio.
