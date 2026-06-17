# HANDOFF

Notas de handoff entre fases. Se actualiza al cerrar cada fase.

## Estado actual

- **Fase en curso:** Fase 1 — Hermes vivo por Discord (artefactos construidos; validación pendiente del VPS).
- **Rama:** `feat/f1-hermes-deploy`.

## Fase 0 — Bootstrap (en curso)

Entregado:
- Estructura de carpetas del plan (`docs/adr`, `config/`, `queue/`, `deploy/`, `scripts/`).
- Tooling Python: `pyproject.toml` (uv) + Ruff, `.pre-commit-config.yaml`.
- CI de lint: `.github/workflows/ci.yml` (`uv run ruff check` + format check).
- `deploy/.env.example` con los nombres de variables, sin valores.
- `docs/runbook.md` (esqueleto), `README.md`, `ADR-0001`.
- `.gitignore` que bloquea cualquier `.env` real.

## Decisiones ya tomadas (para fases siguientes)

- **Proveedor LLM:** OpenRouter. **Modelo:** `moonshotai/kimi-k2.6` (a fijar en `config.yaml`, Fase 1).
- **Sandbox de Hermes:** backend `ssh` / host (Fase 1). Reevaluar Docker antes de las acciones sobre GitHub (Fase 3).
- **VPS recomendado:** Oracle Cloud "Always Free" (ARM Ampere; fallback AMD x86 o GCP `e2-micro`).

## Fase 1 — Hermes deploy (artefactos construidos, validación pendiente)

Entregado (no requiere VPS):
- `config/hermes/config.yaml`: OpenRouter + `moonshotai/kimi-k2.6`, Discord + allowlist,
  `approvals.mode: manual` + `cron_mode: deny`, sandbox `ssh`, `terminal.cwd` seguro.
- `deploy/systemd/hermes-gateway.service`: usuario no-root, restart on-failure, arranque automático.
- `deploy/install-notes.md`: pasos completos de despliegue + checklist de validación.
- `docs/adr/ADR-0002-hermes-deploy.md` (estado: propuesto, se confirma al validar en el VPS).

Pendiente de validación (requiere VPS): que el bot responda/deniegue y sobreviva reboot.
Hay supuestos a reconciliar en el VPS: nombres de campos del `config.yaml` y ruta del
binario en `ExecStart` (ver ADR-0002 e install-notes.md, paso 6).

## Pasos manuales PENDIENTES (humano)

- [ ] **(Fase 1) Provisionar el VPS** — Oracle requiere tarjeta; pospuesto a pedido del usuario.
  - La clave SSH pública ya existe en la PC del usuario: `~/.ssh/id_ed25519.pub`.
- [ ] (Fase 1) Instalar Hermes en el VPS.
- [ ] (Fase 1) Crear el bot de Discord (token + `DISCORD_ALLOWED_USERS`).
- [ ] (Fase 1) Generar la API key de OpenRouter.
- [ ] (Fase 1) Cargar `~/.hermes/.env` con los secrets (chmod 600).

## Próxima fase

- **Fase 1** — config de Hermes (`config.yaml`), unit systemd `hermes-gateway`,
  `install-notes.md` y ADR-0002. La construcción de estos artefactos no depende del VPS;
  la **validación** sí (requiere el VPS provisionado).
