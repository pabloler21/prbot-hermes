# Runbook de operación

> Esqueleto inicial (Fase 0). Se completa a medida que avanzan las fases.

## Servicios

| Servicio | Unit systemd | Estado |
|---|---|---|
| Hermes gateway | `hermes-gateway.service` | se define en Fase 1 |
| Redis | `redis.service` | se define en Fase 4 |
| Workers BullMQ | `bullmq-workers.service` | se define en Fase 4 |

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

- Política de reintentos / backoff: _pendiente._
- Revisión de dead letter: _pendiente._
- Rate limiting por cola: _pendiente._
