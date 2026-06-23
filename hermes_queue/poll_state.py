"""Estado de los jobs de POLL en Redis: cursor + dedup de lo ya avisado.

Un job de poll corre cada pocos minutos y debe: (a) mirar solo lo nuevo desde la última
corrida, y (b) no avisar dos veces lo mismo. Acá viven las dos piezas:

- **Cursor** (`cursor:<name>`): timestamp ISO de la última corrida. Acota la ventana que le
  pedimos a GitHub (no traer todo el historial cada vez).
- **Seen-set** (`seen:<name>`): un sorted-set de ids ya notificados (score = timestamp), para
  deduplicar como cinturón y tiradores ante bordes (p. ej. si el cursor no se actualizó por
  un fallo). Se acota a MAX_SEEN ids para no crecer sin límite (importa en 1GB).

En la PRIMERA corrida no hay cursor: el job setea el baseline ("desde ahora") y NO avisa nada
histórico — solo lo que aparezca DESPUÉS del deploy.
"""

from __future__ import annotations

from datetime import datetime

from arq.connections import ArqRedis

CURSOR_PREFIX = "cursor:"
SEEN_PREFIX = "seen:"
# Máximo de ids recordados por workflow (acota memoria).
MAX_SEEN = 500


def _cursor_key(name: str) -> str:
    return f"{CURSOR_PREFIX}{name}"


def _seen_key(name: str) -> str:
    return f"{SEEN_PREFIX}{name}"


async def get_cursor(redis: ArqRedis, name: str) -> datetime | None:
    """Devuelve el cursor (timestamp de la última corrida) o None si nunca corrió."""
    raw = await redis.get(_cursor_key(name))
    if raw is None:
        return None
    value = raw.decode() if isinstance(raw, bytes) else raw
    return datetime.fromisoformat(value)


async def set_cursor(redis: ArqRedis, name: str, ts: datetime) -> None:
    """Guarda el cursor de la última corrida (ISO 8601)."""
    await redis.set(_cursor_key(name), ts.isoformat())


async def mark_seen(redis: ArqRedis, name: str, item_id: str, ts: datetime) -> bool:
    """Marca un id como visto. Devuelve True si es NUEVO (no avisado antes), False si ya estaba.

    Usa ZADD NX (agrega solo si no existe) y recorta los más viejos al superar MAX_SEEN.
    """
    key = _seen_key(name)
    # nx=True: no piso el score si el id ya estaba -> added=0 indica "ya visto".
    added = await redis.zadd(key, {item_id: ts.timestamp()}, nx=True)
    if added:
        # Recorta los más viejos (rank 0 = menor score) si pasamos el tope.
        await redis.zremrangebyrank(key, 0, -(MAX_SEEN + 1))
    return bool(added)
