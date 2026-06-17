# ADR-0002 — Despliegue del gateway de Hermes (Fase 1)

- **Estado:** confirmado (validado en VPS 2026-06-17)
- **Fase:** 1
- **Fecha:** 2026-06-17

## Contexto

Antes de darle a Hermes cualquier permiso sobre GitHub, se valida la base operativa:
gateway vivo y persistente en el VPS, respondiendo por Discord solo a usuarios
autorizados, y sobreviviendo reinicios. Esta fase produce la configuración y los
artefactos de despliegue; la validación ocurre cuando el VPS esté provisionado.

## Decisiones

1. **Modelo LLM: `kimi-k2.7-code` vía OpenCode.** El usuario tiene suscripción Go activa
   en OpenCode, lo que evita costos variables por token. La API key se lee del entorno
   (`OPENCODE_API_KEY`), no se hardcodea. OpenRouter quedó descartado.

2. **Sandbox backend `ssh`/host.** Más simple para la Fase 1 (sin instalar Docker); no hay
   acciones sobre GitHub todavía y `approvals.mode: manual` gatea los comandos peligrosos.
   Se reevaluará `docker` antes de habilitar acciones sobre GitHub (Fase 3).

3. **`approvals.mode: manual` + `cron_mode: deny` desde el inicio.** Postura segura por
   defecto (fail-closed): todo comando de shell peligroso requiere aprobación yes/no.

4. **Allowlist de usuarios de Discord explícita.** Sin allow-all; sin allowlist Hermes
   deniega a todos. IDs en `DISCORD_ALLOWED_USERS`.

5. **Gateway como servicio systemd, usuario no-root.** `hermes-gateway.service` corre como
   el usuario `hermes`, con `Restart=on-failure` y `WantedBy=multi-user.target` (arranque
   automático tras reboot). `terminal.cwd=/home/hermes/work` para no operar desde
   directorios sensibles.

6. **Secrets solo en `~/.hermes/.env` (chmod 600).** Nunca en el config ni en el repo.

## Supuestos reconciliados (al validar en VPS)

- **Ruta real del binario:** `/home/hermes/.hermes/hermes-agent/venv/bin/hermes`
  (el instalador crea un venv dentro de `hermes-agent/`; no es `~/.hermes/bin/hermes`
  como se asumía inicialmente). Corregido en `deploy/systemd/hermes-gateway.service`.
- **TimeoutStopSec:** el `drain_timeout` de Hermes es 180s; el default de systemd (90s)
  causaría SIGKILL a mitad del drain. Se fijó `TimeoutStopSec=210` en el service.
- **VPS:** Oracle Cloud Always Free, VM.Standard.E2.1.Micro (AMD x86, 1 GB RAM),
  Ubuntu 22.04, IP `137.131.202.213`. ARM Ampere descartado por falta de capacidad
  en São Paulo AD-1.
- **Intents de Discord:** el instalador no habilita automáticamente los Privileged Gateway
  Intents en el Developer Portal. Deben activarse manualmente: Presence, Server Members
  y Message Content Intent.

## Consecuencias

- Quedan listos `config/hermes/config.yaml`, `deploy/systemd/hermes-gateway.service` y
  `deploy/install-notes.md` para desplegar en cuanto haya VPS.
- El cierre de la fase (checklist de validación) queda pendiente del VPS.
