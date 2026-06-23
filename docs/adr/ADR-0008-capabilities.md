# ADR-0008 — Capacidades: triage de issues + lectura de documentación

- **Estado:** aceptado
- **Fase:** 5
- **Fecha:** 2026-06-23

> **Nota de numeración:** el plan (`plan-1-agente-hermes.md`) rotula esta fase como
> "ADR-0006", pero ese número (lenguaje de cola) y ADR-0007 (hardening) ya estaban
> usados por la evolución real del proyecto. Este ADR toma el próximo libre, **0008**.

## Contexto

La Fase 5 suma **capacidades de criterio** sobre la base ya endurecida (Fases 3 y 4):

1. **Triage de issues:** Hermes lee un issue, propone labels/prioridad y/o un comentario.
2. **Lectura de documentación del repo:** Hermes usa los docs como contexto.

El plan es explícito en que **toda salida visible pasa por el approval gate** y que
**triage y docs solo operan sobre repos de la allowlist**. La fase es **reactiva**
(disparada por una consulta en Discord), no introduce workers de *poll* automáticos —
esos aparecen recién en la Fase 6 (digest con `cron_jobs`).

## Decisión

**1. Reutilizar la infra, agregar una sola acción nueva (etiquetar).**
- **Comentar issues:** ya funcionaba. Un PR es un issue para la API, así que el endpoint
  `/issues/{n}/comments` y la tool `propose_pr_comment` sirven igual para issues. Solo se
  amplió el docstring de la tool (PR **o** issue). Cero código nuevo.
- **Leer issues y docs:** ya disponible vía la MCP de GitHub solo-lectura (validado en 3a,
  Hermes leyó `CLAUDE.md`). Es uso de contexto + prompt, no código nuevo. Se resume para
  controlar tokens.
- **Aplicar labels:** lo único realmente nuevo. Camino de escritura espejo del de comentar.

**2. Generalizar el approval gate para que sea agnóstico de la acción.**
- El pedido pendiente ahora guarda `{"task": <nombre>, "data": <payload>}`; `approve()`
  encola la task que indica el pedido. El gate (`jobs/gate.py`) y el bot ✅/❌ dejaron de
  conocer la acción concreta: el bot muestra un `summary` ya formateado por el productor
  (`events.publish_pending(kind, summary)`). Agregar una acción futura = nueva tool +
  nuevo tipo de pedido + función en el worker, sin tocar gate ni bot.

**3. Una sola función nueva en el mismo worker (sin nuevo servicio systemd).**
- `apply_issue_labels` se registra junto a `post_comment` en `WorkerSettings.functions`.
  El servicio `hermes-arq-worker` y el comando `arq --check` no cambian.

## Alternativas consideradas

- **Tool única `propose_issue_triage` (labels + comentario en una aprobación).** Mejor UX
  pero el worker maneja dos llamadas a GitHub y fallo parcial. Descartada por complejidad
  para el alcance/plazo. Dos tools independientes son más simples y sólidas hoy.
- **Job genérico `github-action` con `action_type`.** Más extensible pero abstracto y más
  difícil de defender; YAGNI para dos acciones. Descartada.
- **Nuevo worker/servicio para labels.** Sumaría superficie de despliegue (otra unit
  systemd) sin beneficio: arq corre varias funciones en un mismo worker.

## Consecuencias

- Nuevos: `jobs/gate.py` (gate genérico), `jobs/apply_labels.py` (tipo + idempotencia),
  tool `propose_issue_labels`, task `apply_issue_labels`, `github_client.add_issue_labels`.
- `jobs/post_comment.py` queda solo con el tipo de dato + idempotencia (el gate se fue a
  `gate.py`). `events.publish_pending` y `deadletter` ahora son genéricos (DLQ por task:
  `dead-letter:<task>`).
- **Idempotencia de labels orden-insensible:** se ordenan las labels antes de hashear, así
  el mismo conjunto en distinto orden no genera ids distintos.
- **PASO MANUAL (humano) al desplegar:** `git pull` + reiniciar `hermes-gateway` (re-spawnea
  la MCP y toma la tool nueva) y `hermes-arq-worker`. **Verificar que el PAT puede
  etiquetar** — el endpoint de labels requiere `Issues: write` o `Pull requests: write`
  (verificado en docs.github.com, 2026-06-23). Si da 403, bumpear el permiso del PAT en
  GitHub (editable in-place, sin tocar `.env`).
