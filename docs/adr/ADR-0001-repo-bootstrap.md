# ADR-0001 — Bootstrap del repo de operaciones

- **Estado:** aceptado
- **Fase:** 0
- **Fecha:** 2026-06-16

## Contexto

Se necesita un repo versionado para operar un bot de equipo sobre Hermes Agent + BullMQ.
El repo debe alojar configuración, guardrails y colas/workers, con tooling de calidad y CI
mínima, antes de desplegar nada.

## Decisiones

1. **Versionar configuración y workers, no forkear Hermes.** Hermes se opera como
   dependencia (instalación por CLI en el VPS). Lo versionado es `config.yaml`, los
   guardrails y las colas/workers de BullMQ. Menor superficie de mantenimiento.

2. **Tooling Python con uv + Ruff.** El repo aloja tooling/scripts propios en Python.
   uv para entorno y ejecución; Ruff para lint y formato. CI mínima corre
   `uv run ruff check` + `ruff format --check`.

3. **Estructura agnóstica del lenguaje de workers.** Las carpetas `queue/{workers,jobs}/`
   quedan vacías (`.gitkeep`). La elección TypeScript vs Python para los workers de BullMQ
   se difiere a la Fase 4 y se registrará en ADR-0005, como indica el plan.

4. **Una rama por fase (`feat/fX-nombre`).** `main` refleja la configuración desplegada;
   se mergea con el checklist de la fase cumplido. Cada merge actualiza `HANDOFF.md` y
   agrega el/los ADR.

5. **Secrets fuera del repo.** Solo se versiona `deploy/.env.example` (nombres sin valores).
   `.gitignore` bloquea cualquier `.env` real. En producción los secrets viven en
   `~/.hermes/.env` (chmod 600).

## Supuestos explícitos

- Proveedor LLM: **OpenRouter**; modelo **`moonshotai/kimi-k2.6`** (se fija en Fase 1).
- Sandbox de Hermes: backend **`ssh`/host** (Fase 1); se reevalúa Docker en Fase 3.
- VPS recomendado: **Oracle Cloud Always Free** (ARM Ampere; fallback AMD x86 / GCP `e2-micro`).
  Provisión pospuesta a pedido del usuario (Oracle pide tarjeta). No bloquea Fase 0 ni la
  construcción de artefactos de Fase 1.
- El directorio del repo es `prbot-hermes`, tratado como el repo `team-agent-ops` del plan.

## Consecuencias

- Repo que pasa `uv run ruff check` en CI, con estructura y `.env.example` definidos.
- La decisión de lenguaje de workers queda abierta sin bloquear el avance.
