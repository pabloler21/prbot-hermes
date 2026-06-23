# HANDOFF

Notas de handoff entre fases. Se actualiza al cerrar cada fase.

## Estado actual

- **Fase 3 — MVP end-to-end: COMPLETA y validada en el VPS (2026-06-22).** 3a (lectura),
  Redis asegurado, y 3b (escritura: worker arq + approval gate) funcionando end-to-end.
- **Rama:** `feat/f3-github-mvp` (PR #1), lista para mergear a `main`.

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

- **Fase 4 — Infra de cola durable como servicio de producción** (según el plan, no
  migración de n8n — eso es la Fase 6). Buena parte ya se hizo en 3b (Redis asegurado +
  worker/bot como servicios systemd con reintentos/backoff). Lo que **falta**: dead-letter
  para jobs que agotan reintentos (arq no tiene DLQ nativa), límite de concurrencia
  (`max_jobs`) como rate-limiting, test formal de reboot-survival de los servicios nuevos,
  y observabilidad/runbook de la cola.
- Roadmap restante: Fase 5 = triage de issues + lectura de docs; Fase 6 = digest diario
  (`cron_jobs`) + paridad n8n; Fase 7 = cutover (retirar n8n).
- **Pendiente menor (no bloqueante):** Hermes hoy responde solo por DM, no en el canal del
  server (quirk del home channel). Revisar `DISCORD_HOME_CHANNEL` en `~/.hermes/.env`.
