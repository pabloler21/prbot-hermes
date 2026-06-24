# ADR-0010 — Paridad n8n: los 4 workflows restantes (2 cron + 2 poll)

- **Estado:** aceptado
- **Fase:** 6b
- **Fecha:** 2026-06-23

## Contexto

La Fase 6a entregó el Daily PR Digest. Para alcanzar **paridad con n8n** (criterio de cutover
de la Fase 7, ver `docs/n8n-inventory.md`) faltan los otros 4 workflows del inventario:

| Workflow | Tipo | Schedule | Detección |
|---|---|---|---|
| Stale PR Alert | cron | lun-vie 10:00 | PRs abiertos con `updated_at` > 3 días |
| Weekly Summary | cron | vie 18:00 | PRs mergeados + issues cerrados en 7 días |
| New Issue Alert | poll | cada 5 min | issues nuevos desde la última corrida |
| Deploy Notification | poll | cada 5 min | PRs mergeados a `main` desde la última corrida |

Los 2 cron son "foto del estado actual" (sin estado). Los 2 **poll** son lo nuevo: corren
seguido y deben detectar SOLO lo nuevo sin avisar dos veces. Eso requiere estado en Redis.

## Decisión

**1. Reusar el patrón de la 6a.** Todos son `cron_jobs` de arq en el mismo worker (un solo
scheduler, sin servicio nuevo), entregan por el mismo webhook (`discord_client`), son
deterministas (sin LLM) y SIN approval gate (solo leen GitHub + postean en nuestro canal).
"Cada 5 min" = `cron(minute={0,5,...,55})`.

**2. Mecanismo de poll = cursor + dedup (`hermes_queue/poll_state.py`).**
- **Cursor** (`cursor:<workflow>:<repo>`): timestamp ISO de la última corrida; acota la
  ventana que se le pide a GitHub.
- **Baseline en la 1ª corrida:** sin cursor, se fija "desde ahora" y **no se avisa nada
  histórico** — solo lo que aparezca después del deploy. (Si no, el primer poll dispararía
  una alerta por cada issue/merge viejo.)
- **Dedup** (`seen:<workflow>:<repo>`): sorted-set de ids ya avisados (cinturón y tiradores
  ante bordes, p. ej. si el cursor no se actualizó por un fallo). Acotado a 500 ids por
  workflow (memoria, 1GB). Idempotencia = `repo+issue_number` (issues) y
  `repo+pr_number+merged_at` (deploys), como pide el inventario.

**3. Rate-limiting de poll = el `max_jobs=2` existente.** Es el primer trabajo automático que
genera caudal contra GitHub. Hoy alcanza: 2 polls cada 5 min sobre 1 repo es ínfimo frente al
rate-limit de GitHub (5000 req/hora autenticado). **Se reevaluará** un token-bucket por QPS si
crece el número de repos/workflows (ver ADR-0007). No es necesario ahora (YAGNI).

**4. Rama de deploy = `main`** (constante `DEPLOY_BRANCH` en el worker), la default del repo.

## Alternativas consideradas

- **Webhooks de GitHub en vez de poll** (push, sin latencia de 5 min). Descartado: registrar
  un webhook en el repo requiere permisos de admin; el PAT está scopeado al mínimo
  (defensa en profundidad). El poll es el precio de no pedir admin. Ya estaba decidido en el
  inventario (Fase 2).
- **Solo cursor, sin seen-set.** Más simple, pero un fallo entre "postear" y "actualizar
  cursor" duplicaría el aviso. El seen-set lo evita; el costo (un sorted-set chico) es bajo.
- **Marcar visto ANTES de postear (no después).** Evitaría doble-aviso si el post falla a
  mitad, pero perdería el aviso entero ante un fallo de red. Preferimos el riesgo de un
  doble-aviso raro (mitigado por el seen-set) sobre perder un aviso.

## Consecuencias

- Nuevos: `poll_state.py` (cursor + dedup), `jobs/reports.py` (stale + weekly, deterministas),
  `jobs/alerts.py` (formateadores de los poll). `github_client` suma `list_recently_merged_prs`,
  `list_recently_closed_issues`, `list_new_issues` y `updated_at` en `list_open_pull_requests`.
- El worker suma 4 corutinas + 4 entradas en `cron_jobs` (total 5 con el digest).
- **Paridad alcanzada:** los 5 workflows del inventario tienen su equivalente. Habilita el
  criterio de cutover de la Fase 7 (tras 7 días sin errores en producción).
- **PASO MANUAL:** ninguno nuevo (reusa el webhook de la 6a). Validación: disparar cada job a
  mano (ver runbook) e inspeccionar los cursores/seen-sets en Redis.
- Operación: los cursores y seen-sets son claves de Redis inspeccionables; resetear un poll =
  borrar su `cursor:*` (vuelve a fijar baseline en la próxima corrida).
