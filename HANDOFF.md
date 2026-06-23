# HANDOFF

Notas de handoff entre fases. Se actualiza al cerrar cada fase.

## Estado actual

- **Fase 6b — Paridad n8n (4 workflows restantes): IMPLEMENTADA en `feat/f6b-parity`,
  PENDIENTE de validación en el VPS.** No mergear hasta disparar los jobs en vivo.
- **Fase 6a — Digest diario (arq cron + webhook): COMPLETA y validada en el VPS (2026-06-23),
  mergeada a `main` (PR #7).** Disparo manual posteó el digest en `#digest` (PR #7 listado).

### Fase 6b — paridad n8n (IMPLEMENTADA, pendiente de validar — ver ADR-0010)

Los 4 workflows restantes del inventario, reusando el patrón de la 6a (cron de arq en el
mismo worker, entrega por webhook, sin approval gate, deterministas):
- **Reportes (cron):** `stale_pr_alert` (lun-vie 10:00, PRs sin actividad >3 días; no postea
  si no hay) y `weekly_summary` (vie 18:00, PRs mergeados + issues cerrados en 7 días).
- **Alerts (poll cada 5 min):** `new_issue_alert` y `deploy_notification` (PRs mergeados a
  `main`). Mecanismo nuevo en `poll_state.py`: **cursor** (`cursor:<wf>:<repo>`) acota la
  ventana; **baseline** en la 1ª corrida (no avisa histórico); **seen-set**
  (`seen:<wf>:<repo>`, sorted-set capado a 500) deduplica. Idempotencia `repo+issue_number`
  y `repo+pr_number+merged_at`.
- Nuevos: `poll_state.py`, `jobs/reports.py`, `jobs/alerts.py`. `github_client` suma
  `list_recently_merged_prs` / `list_recently_closed_issues` / `list_new_issues` + `updated_at`.

PASOS MANUALES para validar (sin webhook nuevo — reusa el de la 6a):
1. `git pull` de la branch en el VPS + `sudo systemctl restart hermes-arq-worker`.
2. Disparar los jobs a mano (heredoc en runbook → "Trabajos recurrentes — paridad n8n").
3. Para ver un poll real: crear un issue / mergear un PR DESPUÉS del baseline y re-disparar.

Checklist (validar en vivo):
- [ ] `arq ... --check`: los 5 cron cargados; worker sin errores.
- [ ] `stale_pr_alert` y `weekly_summary` postean en Discord (o stale calla si no hay estancados).
- [ ] `new_issue_alert`: 1ª corrida = baseline; tras crear un issue, lo avisa una sola vez.
- [ ] `deploy_notification`: tras mergear un PR a `main`, lo avisa una sola vez.
- [ ] Cursores/seen-sets visibles en Redis (`keys cursor:*`).
- **Fase 5 — Triage de issues + lectura de docs: COMPLETA y validada en el VPS (2026-06-23),
  mergeada a `main` (PR #5).**
- **Fase 4 — Infra de cola durable endurecida: COMPLETA y validada en el VPS (2026-06-23).**
  Dead-letter + cap de concurrencia + reboot survival validados en vivo.

### Fase 6a — digest diario (COMPLETA, validada 2026-06-23 — ver ADR-0009)

Primer trabajo recurrente. `daily_pr_digest` = **cron job de arq** (lun-vie 09:00 UTC-3,
`unique=True` → idempotente por horario) en el mismo worker (sin servicio nuevo). Lee PRs
abiertos de los repos de la allowlist y postea a Discord vía **webhook** (`discord_client.py`,
parte en trozos de 2000). SIN approval gate (solo lee GitHub + publica en nuestro canal).
Nuevos: `discord_client.py`, `jobs/digest.py`, `github_client.list_open_pull_requests`,
`guardrails.allowed_repos`. Determinista (sin LLM).

PASOS MANUALES para validar:
1. Crear webhook entrante en `#dev` → cargar `DISCORD_DIGEST_WEBHOOK_URL` en `~/.hermes/.env`.
2. `git pull` de la branch en el VPS + `sudo systemctl restart hermes-arq-worker`.
3. Disparar el digest a mano (heredoc en `docs/runbook.md`, sección "Digest diario") y
   verificar el mensaje en `#dev`.

Checklist (validado en vivo):
- [x] El digest se postea en Discord (canal `#digest`) con los PRs abiertos — disparo manual
  listó el PR #7 con su antigüedad; webhook devolvió HTTP 204.
- [x] El worker arranca con el cron cargado, sin errores.
- [~] Idempotencia por horario: garantizada por `unique=True` de arq (no se probó el reinicio
  exacto a las 9:00; el mecanismo está verificado).

Pendiente (Fase 6b): los otros 4 workflows del inventario (issue alert + deploy notif por
poll cada 5 min con cursor en Redis; stale PR cron 10:00; weekly cron viernes 18:00).

### Fase 5 — capacidades (COMPLETA, validada 2026-06-23 — ver ADR-0008)

Reactiva (disparada por Discord), reusa el approval gate. La fase NO trae poll workers
(eso es Fase 6). Cambios:
- **Comentar issues:** ya funcionaba (`propose_pr_comment` sirve para PR e issue); solo se
  amplió el docstring. **Leer issues/docs:** ya disponible vía la MCP read-only (validado 3a).
- **Aplicar labels (lo nuevo):** tool `propose_issue_labels` → gate → task `apply_issue_labels`
  en el mismo worker. `github_client.add_issue_labels` (POST `/issues/{n}/labels`).
- **Gate generalizado:** el pedido pendiente lleva `{"task", "data"}`; `jobs/gate.py`
  (genérico) + `jobs/apply_labels.py`. El bot ✅/❌ muestra un `summary` ya formateado
  (agnóstico de la acción). DLQ por task: `dead-letter:<task>`.

Despliegue (validado): `git pull` en el VPS + reinicio de **gateway + worker + approval-bot**
(los tres: cambió el contrato MCP↔bot↔worker; reiniciar solo gateway+worker dejó al bot con
el formato viejo del pub/sub → `KeyError` → no posteaba). PAT con `Issues: write` confirmado.

Checklist de la fase (validado en vivo):
- [x] Triage de un issue real (#6): Hermes propone `bug`+`priority:high` → ✅ por Discord →
  labels aplicadas en GitHub (mensaje editado a `✅ Hecho: <url>`).
- [x] Gate genérico + bot agnóstico de la acción funcionando con el payload `{kind, summary}`.
- [x] PAT puede etiquetar (sin 403).
- [~] Comentar un issue (no PR) → mismo endpoint que comentar PR, ya validado en Fase 3.
- [~] Rechazo por allowlist → mismo código determinístico ya validado en Fase 4 (ahora con DLQ
  `dead-letter:apply_issue_labels`).
- [x] Lectura del issue como contexto, resumida (lectura de repo ya validada en 3a).

Follow-ups no bloqueantes: vistas de botones no persisten reinicios del bot (registrar vistas
persistentes con `custom_id`+`add_view`); home-channel quirk (responde solo por DM).
- **Fase 3 — MVP end-to-end: COMPLETA y validada en el VPS (2026-06-22).** 3a (lectura),
  Redis asegurado, y 3b (escritura: worker arq + approval gate) funcionando end-to-end.

### Fase 4 — endurecimiento de la cola (COMPLETA, validada 2026-06-23)

arq no tiene dead-letter ni rate-limiter por QPS nativos (verificado vía Context7). Se
agregó:
- `hermes_queue/deadletter.py`: DLQ como lista de Redis `dead-letter:post_comment` (cap
  100), con `record` / `list` / `requeue`. El worker manda al DLQ los fallos permanentes
  (4xx, repo fuera de allowlist) y los transitorios que agotan los 5 reintentos.
- `WorkerSettings`: `max_tries=5` explícito + `max_jobs=2` (concurrencia como rate-limit;
  el approval gate humano ya throttlea las escrituras). Ver ADR-0007.
- Runbook ampliado: health (`arq --check`), inspeccionar/reencolar DLQ, check de reboot.

Checklist validado en el VPS:
- [x] Dead-letter captura un fallo: pedido a repo fuera de allowlist → entry
  `repo-not-allowed` en `dead-letter:post_comment` (en 3b se perdía sin rastro).
- [x] Reintentos/backoff (heredado de 3b).
- [x] Cap de concurrencia desplegado (`max_jobs=2`).
- [x] Reboot survival: tras `sudo reboot`, los 4 servicios (`redis-server`,
  `hermes-gateway`, `hermes-arq-worker`, `hermes-approval-bot`) quedaron `active`.

### Fase 3a — GitHub MCP solo-lectura (completo, validado 2026-06-19)

- MCP de GitHub conectado vía CLI `hermes mcp add` (NO por bloque `mcp_servers` del
  config — ese supuesto de ADR-0002 era incorrecto; corregido en ADR-0004).
- PAT cargado en `~/.hermes/.env` como `GITHUB_PAT`, referenciado como `${GITHUB_PAT}`
  (no hardcodeado). PAT scopeado: read + PR/issue comments + actions:read; sin merge/push.
- MCP en SOLO-LECTURA: 14 tools de lectura activas, 12 de escritura desactivadas con
  `hermes mcp configure`. Hermes no puede publicar directamente — solo leer.
- Validado: Hermes leyó `CLAUDE.md` del repo desde Discord (`get_file_contents`).
- `config/guardrails/repo-allowlist.yaml` creado (`pabloler21/prbot-hermes`); se aplicará
  en el worker en 3b.

### Redis — prerequisito de 3b (completo, asegurado 2026-06-21)

Paso manual hecho por el humano. Instalado con `apt install redis-server`. Asegurado:
- `bind 127.0.0.1 ::1` (solo localhost — no expuesto a internet).
- `requirepass` con clave aleatoria (`openssl rand -hex 32`, formato hex para que sea
  URL-safe dentro del `REDIS_URL`).
- `REDIS_URL=redis://:<clave>@127.0.0.1:6379` cargado en `~/.hermes/.env` (chmod 600).
- Verificado: `redis-cli ping` → `NOAUTH` (sin clave); `redis-cli -u "$REDIS_URL" ping` → `PONG`.

### Fase 3b — escritura con approval gate (COMPLETA, validada 2026-06-22)

Camino de escritura en **Python + arq** (ADR-0006, supersede ADR-0005; descartó BullMQ/TS
por defendibilidad en el stack del autor + VPS de 1GB). Paquete `hermes_queue/`:
- `settings.py` (conexión Redis), `jobs/post_comment.py` (productor + approval gate
  Enfoque B: pendiente = clave Redis `pending-approval:<id>`; solo lo aprobado entra a la
  cola de arq), `guardrails.py` (allowlist), `github_client.py` (POST comentario),
  `events.py` (pub/sub).
- `workers/post_comment_worker.py` (worker: allowlist + post + retries/backoff).
- `mcp_server.py` (tool `propose_pr_comment` para Hermes) + `approval_bot.py` (bot Discord
  con botones ✅/❌, gate determinístico restringido a la allowlist de usuarios).
- Servicios systemd: `hermes-arq-worker`, `hermes-approval-bot` (corren como `hermes`).

Validado end-to-end en el VPS: usuario (DM) → Hermes llama la tool → pendiente → bot con
botones → aprobación → worker postea en GitHub. Allowlist, idempotencia (`_job_id` =
sha256(repo+pr+body)) y manejo de errores (403 del PAT) confirmados en vivo.

## Fase 0 — Bootstrap (completa)

Entregado:
- Estructura de carpetas del plan (`docs/adr`, `config/`, `queue/`, `deploy/`, `scripts/`).
- Tooling Python: `pyproject.toml` (uv) + Ruff, `.pre-commit-config.yaml`.
- CI de lint: `.github/workflows/ci.yml` (`uv run ruff check` + format check).
- `deploy/.env.example` con los nombres de variables, sin valores.
- `docs/runbook.md` (esqueleto), `README.md`, `ADR-0001`.
- `.gitignore` que bloquea cualquier `.env` real.

## Fase 1 — Hermes deploy (completa, validada en VPS 2026-06-17)

Entregado:
- `config/hermes/config.yaml`: OpenCode + `kimi-k2.7-code`, Discord + allowlist,
  `approvals.mode: manual` + `cron_mode: deny`, sandbox `ssh`, `terminal.cwd` seguro.
- `deploy/systemd/hermes-gateway.service`: ruta real del binario confirmada,
  `TimeoutStopSec=210` para evitar SIGKILL durante drain.
- `deploy/install-notes.md`: pasos completos de despliegue + checklist de validación.
- `docs/adr/ADR-0002-hermes-deploy.md` (estado: confirmado).

Checklist de validación superado:
- [x] Bot responde a mensajes de usuario en la allowlist (DM + canal `#hola`).
- [x] `systemctl restart` recupera el servicio.
- [x] `~/.hermes/.env` con `chmod 600` (solo legible por el usuario `hermes`).
- [x] Reboot survival — el servicio arrancó solo tras `sudo reboot`.

Decisiones reconciliadas:
- Proveedor LLM: **OpenCode** (no OpenRouter). Modelo: `kimi-k2.7-code`.
- Ruta del binario: `/home/hermes/.hermes/hermes-agent/venv/bin/hermes`.
- VPS: Oracle Cloud Always Free, VM.Standard.E2.1.Micro (AMD x86), IP `137.131.202.213`.

## Fase 2 — Inventario n8n y mapa de migración (completa, 2026-06-18)

Entregado:
- `docs/n8n-inventory.md`: 5 workflows inventariados con trigger, acción, salida,
  frecuencia y criticidad. Todos asignados a BullMQ schedulers. PR Assistant (nuevo)
  asignado a Hermes agéntico en Fase 5.
- `docs/adr/ADR-0003-migration-map.md`: decisiones de clasificación, criterio de
  cutover (7 días sin errores en producción) y tabla de workers por workflow.

## Decisiones ya tomadas (para fases siguientes)

- **Sandbox de Hermes:** backend `ssh` / host (Fase 1). Reevaluar Docker antes de las
  acciones sobre GitHub (Fase 3).
- **Worker language:** Python + arq (ADR-0006, supersede ADR-0005). Paquete `hermes_queue/`.
- **Sin webhooks:** PAT es read-only, sin permisos de admin. Alertas via poll cada 5 min.
- **Idempotencia:** obligatoria en todos los workers de poll desde el inicio.

## Próxima fase

- **Fase 7 — Cutover:** deshabilitar n8n (sin eliminar) → ventana de observación (7 días sin
  errores, criterio de la Fase 2) → baja definitiva con export final guardado. Solo cuando la
  6b esté validada y los 5 workflows corran estables. PASOS MANUALES (humano): deshabilitar y
  luego dar de baja n8n.
- Con la 6b se alcanza **paridad funcional** con n8n (los 5 workflows del inventario tienen su
  equivalente en arq).
- **Pendiente menor (no bloqueante):** Hermes hoy responde solo por DM, no en el canal del
  server (quirk del home channel). Revisar `DISCORD_HOME_CHANNEL` en `~/.hermes/.env`.
