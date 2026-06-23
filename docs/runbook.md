# Runbook de operación

> Esqueleto inicial (Fase 0). Se completa a medida que avanzan las fases.

## Servicios

| Servicio | Unit systemd | Estado |
|---|---|---|
| Hermes gateway (+ sus MCP) | `hermes-gateway.service` | activo (Fase 1) |
| Redis | `redis-server.service` | activo (asegurado en 3b) |
| Worker arq (post-comment) | `hermes-arq-worker.service` | activo (Fase 3b) |
| Bot de aprobación Discord | `hermes-approval-bot.service` | activo (Fase 3b) |

## Arrancar / parar / estado

```bash
# (Fase 1+) ejemplos con el gateway de Hermes
sudo systemctl status hermes-gateway
sudo systemctl restart hermes-gateway
sudo systemctl stop hermes-gateway
```

## Ver logs

```bash
journalctl -u hermes-gateway -f      # logs del servicio
# y/o
ls ~/.hermes/logs/                    # logs propios de Hermes
```

## Rotar secrets

1. Editar `~/.hermes/.env` en el VPS (mantener `chmod 600`).
2. Reiniciar el servicio afectado (`sudo systemctl restart hermes-gateway`).
3. Verificar que arranca sin errores en los logs.

## Operación de la cola (Fase 4)

Todo se corre en el VPS como usuario `hermes` (dueño del repo y del venv). El `REDIS_URL`
vive en `~/.hermes/.env`; cargalo antes de usar `redis-cli`:

```bash
sudo su - hermes
cd /home/hermes/prbot-hermes
set -a; source ~/.hermes/.env; set +a   # exporta REDIS_URL
```

### Reintentos / backoff

- `max_tries = 5` por job; backoff lineal (5s, 10s, 15s…) vía `Retry(defer=...)`.
- 5xx de GitHub y errores de red = transitorios → se reintentan.
- 4xx (auth, PR inexistente) y repo fuera de la allowlist = permanentes → al dead-letter.

### Health del worker

```bash
# arq escribe una health-check key en Redis; --check sale 0 si está sano.
.venv/bin/arq hermes_queue.workers.post_comment_worker.WorkerSettings --check
```

### Dead-letter (jobs que fallaron definitivamente)

arq no tiene DLQ nativa: la implementamos como una lista de Redis **por task**,
`dead-letter:<task>` (ver `hermes_queue/deadletter.py` y ADR-0007). Hoy hay dos:
`dead-letter:post_comment` y `dead-letter:apply_issue_labels` (Fase 5).

```bash
# Cuántos pedidos fallidos hay acumulados (ajustar la task)
redis-cli -u "$REDIS_URL" llen dead-letter:post_comment
redis-cli -u "$REDIS_URL" llen dead-letter:apply_issue_labels

# Ver los más recientes (JSON con ts, reason y data)
redis-cli -u "$REDIS_URL" lrange dead-letter:post_comment 0 9
```

Reintento manual del más reciente (índice 0) de una task. Reencola sin `_job_id` a
propósito (no lo descarta la idempotencia); es seguro porque el DLQ solo contiene
trabajo ya aprobado:

```bash
.venv/bin/python - <<'PY'
import asyncio
from arq import create_pool
from hermes_queue.settings import redis_settings_from_env
from hermes_queue.deadletter import requeue_dead_letter, list_dead_letters

TASK = "post_comment"  # o "apply_issue_labels"

async def main():
    pool = await create_pool(redis_settings_from_env())
    print("antes:", await list_dead_letters(pool, TASK, 5))
    job_id = await requeue_dead_letter(pool, TASK, index=0)
    print("reencolado:", job_id)
    await pool.aclose()

asyncio.run(main())
PY
```

### Largo de la cola de trabajo

```bash
redis-cli -u "$REDIS_URL" zcard arq:queue   # jobs pendientes/en vuelo en la cola de arq
```

## Digest diario (Fase 6 — trabajo recurrente)

El `daily_pr_digest` es un **cron job de arq** (lun-vie 09:00 UTC-3) registrado en el mismo
worker. Lee los PRs abiertos de los repos de la allowlist y los postea a Discord vía el
**webhook** `DISCORD_DIGEST_WEBHOOK_URL`. No tiene approval gate (solo lee GitHub y publica
en nuestro canal). Ver ADR-0009.

**PASO MANUAL (una vez):** crear el webhook en `#dev` (Editar canal → Integraciones →
Webhooks → Nuevo webhook), copiar la URL y cargarla en `~/.hermes/.env`:

```bash
# como hermes, editar ~/.hermes/.env (mantener chmod 600) y agregar:
# DISCORD_DIGEST_WEBHOOK_URL=https://discord.com/api/webhooks/...
# luego, como ubuntu, recargar el worker para que tome la variable:
sudo systemctl restart hermes-arq-worker
```

**Validar SIN esperar a las 9am** (dispara el digest ahora; ejercita GitHub + webhook reales):

```bash
sudo su - hermes
cd /home/hermes/prbot-hermes
set -a; source ~/.hermes/.env; set +a
.venv/bin/python - <<'PY'
import asyncio
from hermes_queue.workers.post_comment_worker import daily_pr_digest

# La corutina ignora ctx; le pasamos {} para correrla suelta.
asyncio.run(daily_pr_digest({}))
print("digest disparado — revisá #dev en Discord")
PY
```

El cron es idempotente por horario (`unique=True`): un reinicio cerca de las 9:00 no duplica
el envío. Para verificar que el worker tiene el cron cargado: `arq ... --check` (sección Health).

## Trabajos recurrentes — paridad n8n (Fase 6b)

Los 5 workflows (todos cron de arq en el mismo worker, entrega por webhook, sin approval gate):

| Job | Schedule (UTC-3) | Tipo |
|---|---|---|
| `daily_pr_digest` | lun-vie 09:00 | reporte |
| `stale_pr_alert` | lun-vie 10:00 | reporte (no postea si no hay estancados) |
| `weekly_summary` | vie 18:00 | reporte |
| `new_issue_alert` | cada 5 min | poll (cursor + dedup) |
| `deploy_notification` | cada 5 min | poll (cursor + dedup) |

### Disparar cualquier job a mano (validar sin esperar al horario)

```bash
sudo su - hermes
cd /home/hermes/prbot-hermes
set -a; source ~/.hermes/.env; set +a
.venv/bin/python - <<'PY'
import asyncio
from arq import create_pool
from hermes_queue.settings import redis_settings_from_env
from hermes_queue.workers import post_comment_worker as w

async def main():
    # ctx mínimo: las corutinas de poll usan ctx["redis"]; los reportes lo ignoran.
    pool = await create_pool(redis_settings_from_env())
    ctx = {"redis": pool}
    # cambiar por el job a probar:
    await w.stale_pr_alert(ctx)
    await w.weekly_summary(ctx)
    await w.new_issue_alert(ctx)
    await w.deploy_notification(ctx)
    await pool.aclose()
    print("jobs disparados — revisá Discord")

asyncio.run(main())
PY
```

> Nota sobre los poll: la 1ª corrida solo fija el **baseline** (no avisa histórico). Para ver
> un aviso real, creá un issue / mergeá un PR DESPUÉS de esa primera corrida y volvé a dispararlo.

### Inspeccionar / resetear el estado de los poll

```bash
# cursores (timestamp de la última corrida por workflow y repo)
redis-cli -u "$REDIS_URL" keys 'cursor:*'
redis-cli -u "$REDIS_URL" get 'cursor:new_issue:pabloler21/prbot-hermes'

# ids ya avisados (sorted-set, score = timestamp)
redis-cli -u "$REDIS_URL" zrange 'seen:new_issue:pabloler21/prbot-hermes' 0 -1 WITHSCORES

# resetear un poll (vuelve a fijar baseline en la próxima corrida):
redis-cli -u "$REDIS_URL" del 'cursor:new_issue:pabloler21/prbot-hermes'
```

## Supervivencia a reboot (validación Fase 4 — PASO MANUAL)

```bash
# como ubuntu (admin)
sudo reboot
# reconectar tras ~1 min y verificar que los cuatro servicios levantaron solos:
systemctl is-active redis-server hermes-gateway hermes-arq-worker hermes-approval-bot
# deben devolver "active" en las cuatro líneas
```
