# ADR-0002 — Despliegue del gateway de Hermes (Fase 1)

- **Estado:** propuesto (se confirma al validar en el VPS)
- **Fase:** 1
- **Fecha:** 2026-06-17

## Contexto

Antes de darle a Hermes cualquier permiso sobre GitHub, se valida la base operativa:
gateway vivo y persistente en el VPS, respondiendo por Discord solo a usuarios
autorizados, y sobreviviendo reinicios. Esta fase produce la configuración y los
artefactos de despliegue; la validación ocurre cuando el VPS esté provisionado.

## Decisiones

1. **Modelo LLM: `moonshotai/kimi-k2.6` vía OpenRouter.** Elegido por el usuario para el
   bot interno de equipo. La API key se lee del entorno (`OPENROUTER_API_KEY`), no se
   hardcodea.

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

## Supuestos explícitos

- **Nombres de campos del `config.yaml`:** se siguieron los conceptos documentados de
  Hermes (provider OpenRouter, channels.discord, approvals, sandbox, terminal). Los nombres
  exactos (`api_key_env`, `token_env`, `allowed_users_env`, etc.) **deben reconciliarse**
  contra el `config.yaml` que genera el instalador y la doc oficial. Si difieren, se ajusta
  y se actualiza este ADR. (Regla del plan: asumir lo razonable y dejar el supuesto explícito.)
- **Ruta del binario en `ExecStart`:** se asumió `/home/hermes/.hermes/bin/hermes`; debe
  confirmarse con `which hermes` en el VPS.
- **VPS pendiente de provisionar** (Oracle pide tarjeta; pospuesto a pedido del usuario).
  La construcción de estos artefactos no depende del VPS; la validación sí.

## Consecuencias

- Quedan listos `config/hermes/config.yaml`, `deploy/systemd/hermes-gateway.service` y
  `deploy/install-notes.md` para desplegar en cuanto haya VPS.
- El cierre de la fase (checklist de validación) queda pendiente del VPS.
