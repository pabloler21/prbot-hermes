"""Dead-letter para jobs que fallaron de forma definitiva.

arq NO tiene una dead-letter queue nativa: cuando un job agota `max_tries`, marca el
resultado como fallido pero el payload no queda en ninguna cola revisable — se pierde.
Acá lo guardamos nosotros en una lista de Redis por cada task (`dead-letter:<task>`)
para poder inspeccionarlo y, si hace falta, reintentarlo a mano.

El DLQ solo contiene trabajo que YA pasó el approval gate (un humano lo aprobó y se
encoló). Por eso reencolar desde acá es seguro: es re-ejecutar trabajo ya aprobado, no
saltearse la aprobación.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from arq.connections import ArqRedis

# Cap de entradas por lista: en un VPS de 1GB no queremos que crezca sin límite.
MAX_DEAD_LETTERS = 100


def dead_letter_key(task: str) -> str:
    """Clave de la lista de Redis del DLQ de una task (p. ej. dead-letter:post_comment)."""
    return f"dead-letter:{task}"


async def record_dead_letter(pool: ArqRedis, *, task: str, reason: str, data: dict) -> None:
    """Registra un pedido fallido en el DLQ de su task (con motivo y timestamp).

    `data` es el payload del job (el dict que recibe el worker), para poder reencolarlo
    tal cual más adelante.
    """
    entry = json.dumps(
        {
            "ts": datetime.now(UTC).isoformat(),
            "reason": reason,
            "data": data,
        }
    )
    # LPUSH agrega al inicio; LTRIM recorta a los últimos MAX_DEAD_LETTERS para capar
    # el uso de memoria. Las dos operaciones juntas mantienen la lista acotada.
    key = dead_letter_key(task)
    await pool.lpush(key, entry)
    await pool.ltrim(key, 0, MAX_DEAD_LETTERS - 1)


async def list_dead_letters(pool: ArqRedis, task: str, limit: int = 20) -> list[dict]:
    """Devuelve las entradas más recientes del DLQ de una task (las primeras de la lista)."""
    raw = await pool.lrange(dead_letter_key(task), 0, limit - 1)
    # redis-py devuelve bytes; json.loads acepta bytes desde Python 3.6.
    return [json.loads(item) for item in raw]


async def requeue_dead_letter(pool: ArqRedis, task: str, index: int = 0) -> str | None:
    """Reencola un pedido del DLQ de una task por índice (0 = el más reciente).

    Lo encola SIN `_job_id` a propósito: es un reintento manual deliberado, así que no
    queremos que la idempotencia lo descarte por chocar con un resultado viejo en caché.
    Devuelve el id del nuevo job, o None si el índice no existe.
    """
    key = dead_letter_key(task)
    raw = await pool.lindex(key, index)
    if raw is None:
        return None

    entry = json.loads(raw)
    # El nombre de la task de arq coincide con la key del DLQ por convención.
    job = await pool.enqueue_job(task, entry["data"])
    # LREM elimina la primera ocurrencia exacta de esa entrada (la que acabamos de leer).
    await pool.lrem(key, 1, raw)
    return job.job_id if job else None
