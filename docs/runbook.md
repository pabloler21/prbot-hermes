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

arq no tiene DLQ nativa: la implementamos como la lista de Redis `dead-letter:post_comment`
(ver `hermes_queue/deadletter.py` y ADR-0007).

```bash
# Cuántos pedidos fallidos hay acumulados
redis-cli -u "$REDIS_URL" llen dead-letter:post_comment

# Ver los más recientes (JSON con ts, reason y data)
redis-cli -u "$REDIS_URL" lrange dead-letter:post_comment 0 9
```

Reintento manual del más reciente (índice 0). Reencola sin `_job_id` a propósito (no lo
descarta la idempotencia); es seguro porque el DLQ solo contiene trabajo ya aprobado:

```bash
.venv/bin/python - <<'PY'
import asyncio
from arq import create_pool
from hermes_queue.settings import redis_settings_from_env
from hermes_queue.deadletter import requeue_dead_letter, list_dead_letters

async def main():
    pool = await create_pool(redis_settings_from_env())
    print("antes:", await list_dead_letters(pool, 5))
    job_id = await requeue_dead_letter(pool, index=0)
    print("reencolado:", job_id)
    await pool.aclose()

asyncio.run(main())
PY
```

### Largo de la cola de trabajo

```bash
redis-cli -u "$REDIS_URL" zcard arq:queue   # jobs pendientes/en vuelo en la cola de arq
```

## Supervivencia a reboot (validación Fase 4 — PASO MANUAL)

```bash
# como ubuntu (admin)
sudo reboot
# reconectar tras ~1 min y verificar que los cuatro servicios levantaron solos:
systemctl is-active redis-server hermes-gateway hermes-arq-worker hermes-approval-bot
# deben devolver "active" en las cuatro líneas
```
