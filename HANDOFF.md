# HANDOFF

Notas de handoff entre fases. Se actualiza al cerrar cada fase.

## Estado actual

- **Fase en curso:** Fase 3 — MVP end-to-end. **3a (lectura) completo y validado;
  Redis instalado y asegurado; 3b (escritura: worker + approval gate) DESBLOQUEADA,
  próximo trabajo.**
- **Rama activa:** `feat/f3-github-mvp`.

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

### Fase 3b — escritura con approval gate (DESBLOQUEADA, próximo trabajo)

Con Redis listo, se construye el camino de escritura: worker BullMQ `post-comment` +
estado `pending-approval` + aprobación yes/no por Discord + idempotencia (`repo+pr+content_hash`)
+ validación de allowlist de repos en el worker (capa determinística, no en el LLM).
Decisión pendiente antes de codear: lenguaje del worker (TS vs Python) → ADR-0005.

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
- **Worker language:** por decidir en Fase 4 (ADR-0005). Estructura agnóstica hasta entonces.
- **Sin webhooks:** PAT es read-only, sin permisos de admin. Alertas via poll cada 5 min.
- **Idempotencia:** obligatoria en todos los workers de poll desde el inicio.

## Próxima fase

- **Fase 3** — MVP end-to-end: conectar GitHub MCP, allowlist de repos, approval gate
  de publicación en BullMQ, worker `post-comment` con idempotencia.
  Pasos manuales previos: generar PAT de GitHub (read + comments) y definir allowlist.
