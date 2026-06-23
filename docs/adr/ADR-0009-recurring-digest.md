# ADR-0009 — Trabajo recurrente: digest diario (arq cron) + entrega por webhook

- **Estado:** aceptado
- **Fase:** 6 (6a — digest + andamiaje; los otros 4 workflows del inventario van en 6b)
- **Fecha:** 2026-06-23

> **Nota de numeración:** el plan rotula esta fase como "ADR-0007", pero 0007 (hardening) y
> 0008 (capacidades) ya estaban usados por la evolución real. Este toma el próximo libre, 0009.

## Contexto

La Fase 6 cubre la "plomería recurrente" que hacía n8n (ver `docs/n8n-inventory.md`: 5
workflows). Empezamos por el estrella, el **Daily PR Digest**: lun-vie 09:00, postear en
Discord la lista de PRs abiertos esperando review. Decisiones a tomar: cómo schedulear, cómo
entregar a Discord desde un worker que no es bot, y cómo evitar duplicados.

Verificado vía Context7 (arq-docs.helpmanual.io) y el código instalado (arq 0.28.0):
- `arq.cron(coro, *, weekday, hour, minute, ..., unique=True)`. El `job_id` de un cron es
  `f"{name}:{next_run_ms}"` → con `unique=True` (default) un reinicio cerca del horario **no
  duplica** el disparo (la idempotencia es la hora programada).
- `weekday` admite int 0-6 (0=lunes, igual que `datetime.weekday()`) o nombres
  `mon/tues/wed/thurs/fri/sat/sun`. Lun-vie = `{0,1,2,3,4}`.
- `Worker` acepta `timezone: Optional[datetime.timezone]` → scheduling en huso explícito.

## Decisión

**1. Scheduling con `cron_jobs` de arq, en el worker que ya corre.** Un solo mecanismo de
scheduling (lo exige el plan), sin servicio systemd nuevo (1GB de RAM): el mismo worker corre
las tasks por demanda y los cron. `cron(daily_pr_digest, weekday={0,1,2,3,4}, hour=9, minute=0)`.

**2. Timezone explícita = UTC-3 (Argentina), offset fijo.** `timezone(timedelta(hours=-3))`.
Argentina no tiene DST, así que un offset fijo es correcto y simple (no hace falta `zoneinfo`).
Un cron sin TZ explícita es ambiguo ("¿9 de qué huso?") — el plan lo prohíbe.

**3. Idempotencia = la nativa del cron (`unique=True`).** No agregamos clave propia: el
`job_id` por horario ya garantiza un solo envío por día aunque el worker reinicie a las 9:00.

**4. Entrega a Discord por WEBHOOK entrante, no por bot.** El digest solo PUBLICA (no escucha
nada), así que un bot con conexión al gateway sería sobredimensionado. Un webhook es un POST
HTTP sin estado ni proceso. URL en `DISCORD_DIGEST_WEBHOOK_URL` (~/.hermes/.env) — es una
credencial. `discord_client.py` parte el texto en trozos <= 2000 (límite de Discord).

**5. SIN approval gate.** El digest solo lee GitHub y publica en NUESTRO Discord; no escribe
en GitHub. No hay nada que aprobar. (Contraste con las Fases 3-5, donde toda escritura a
GitHub sí pasa por el gate.) Itera sobre los repos de la allowlist (misma fuente determinística).

**6. Digest determinístico (sin LLM).** El inventario (Fase 2) ya lo clasificó así: consultar
la API, formatear, postear. Más barato, confiable y testeable que pasarlo por el modelo.

## Alternativas consideradas

- **Entrega reusando un token de bot (discord.py).** Mantiene/abre conexión al gateway por
  cada envío; reusa credenciales de bot. Descartada: el webhook es más liviano y desacoplado.
- **Entrega vía Hermes (que el LLM postee).** Acopla un trabajo determinístico al LLM (costo,
  no-determinismo). Descartada.
- **Cron de Linux / cron nativo de Hermes.** Sería un segundo mecanismo de scheduling en
  paralelo (fuente clásica de doble-disparo). El plan manda uno solo: el de arq.
- **Servicio systemd aparte para el cron.** Gasta RAM sin necesidad; arq corre cron y tasks
  en el mismo proceso.

## Consecuencias

- Nuevos: `discord_client.py` (webhook + split 2000), `jobs/digest.py` (`build_pr_digest`,
  lógica pura testeable), `github_client.list_open_pull_requests`, `guardrails.allowed_repos`.
- El worker suma la corutina `daily_pr_digest` + `cron_jobs` + `timezone` en `WorkerSettings`.
- **PASO MANUAL (humano):** crear el webhook entrante en el canal `#dev` (Editar canal →
  Integraciones → Webhooks) y cargar `DISCORD_DIGEST_WEBHOOK_URL` en `~/.hermes/.env`. El
  worker ya carga ese `.env` (EnvironmentFile en su unit), así que solo hay que reiniciarlo.
- **Validación sin esperar a las 9am:** disparar el digest a mano (ver runbook).
- **Pendiente (Fase 6b):** los otros 4 workflows del inventario (New Issue Alert y Deploy
  Notification por poll cada 5 min; Stale PR Alert cron 10:00; Weekly Summary cron viernes
  18:00). Reusan este patrón (cron/poll + discord_client). Los de poll suman un cursor en
  Redis + idempotencia `repo+issue_number` / `repo+pr_number+merged_at`, y ahí se reevalúa el
  rate-limiting por QPS (hoy: cap de concurrencia).
