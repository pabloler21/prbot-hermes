# HANDOFF

Notas de handoff entre fases. Se actualiza al cerrar cada fase.

## Estado actual

- **Fase en curso:** Fase 2 — Redis + BullMQ base.
- **Rama activa:** `feat/f2-bullmq-base` (por crear).
- **Rama anterior:** `feat/f1-hermes-deploy` (pendiente de mergear a `main`).

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

## Decisiones ya tomadas (para fases siguientes)

- **Sandbox de Hermes:** backend `ssh` / host (Fase 1). Reevaluar Docker antes de las
  acciones sobre GitHub (Fase 3).
- **Worker language (Fase 4):** por decidir. Ver ADR-0005 cuando llegue.

## Próxima fase

- **Fase 2** — Redis + BullMQ base: instalar Redis en el VPS (bind local, con password),
  crear la estructura de colas/workers en el repo, smoke test con un job de prueba.
