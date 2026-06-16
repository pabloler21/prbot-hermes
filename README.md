# team-agent-ops

Repo de operaciones para desplegar y operar un **bot interno de equipo** construido
sobre **Hermes Agent (Nous Research)** + **BullMQ/Redis**, conectado a **Discord** y
**GitHub**, migrando lo que hoy hace un bot de **n8n** y luego retirándolo.

## Qué es (arquitectura)

- **Hermes Agent** = el cerebro. Recibe mensajes por Discord, razona, decide y dispone
  de tools (GitHub vía MCP, lectura de docs). Corre como gateway 24/7 en un VPS.
- **BullMQ (Redis)** = la capa de ejecución durable. Todo trabajo que actúa sobre GitHub
  o que es recurrente/crítico se encola como job, con reintentos, backoff, deduplicación
  y rate limiting. Sobrevive reinicios, no se duplica y se reintenta ante fallos.
- **Patrón:** Hermes decide y **encola** → un **worker BullMQ** ejecuta la acción →
  el resultado se loguea y se reporta de vuelta a Discord.

Hermes se opera **como dependencia** (no se forkea). Lo que se versiona acá es la
configuración (`config.yaml`), los guardrails y las colas/workers.

## Cómo se despliega

El despliegue es por fases (ver `plan-1-agente-hermes.md`). Los pasos manuales de infra
(crear VPS, instalar Hermes, crear el bot de Discord, generar tokens) están en
`deploy/install-notes.md`. Los artefactos versionados (config, units de systemd) se
copian al VPS según esas notas.

## Cómo se opera

Ver `docs/runbook.md`: arrancar/parar servicios, ver logs, rotar secrets.

## Estructura

```
docs/adr/        # decisiones por fase (ADR-0001...)
docs/            # runbook, inventario de n8n
config/hermes/   # config.yaml de Hermes
config/guardrails/  # allowlist de repos, política de approval
queue/           # BullMQ: colas, workers, jobs
deploy/          # systemd units, .env.example, install-notes
scripts/         # utilidades de operación
```

## Convenciones

- Código en inglés; comentarios/docstrings en español; commits en inglés (Conventional Commits).
- Tooling Python con **uv** + **Ruff** (`uv run ruff check`).
- Secrets solo en `~/.hermes/.env` (chmod 600). Nunca hardcodeados ni commiteados.
- Una rama por fase (`feat/fX-nombre`); merge a `main` con el checklist cumplido.
