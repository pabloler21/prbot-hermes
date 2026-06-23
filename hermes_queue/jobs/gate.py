"""Approval gate (Enfoque B) genérico, agnóstico de la acción.

Tres operaciones sobre la SALA DE ESPERA (una clave de Redis por pedido):
  1. enqueue_pending -> guarda el pedido pendiente (qué task encolar + su payload).
  2. approve         -> el humano dijo "sí"; lo mueve a la cola real de arq.
  3. reject          -> el humano dijo "no"; lo borra. Nunca llega al worker.

El pedido pendiente guarda QUÉ task encolar (`task`) y su payload (`data`), así el
mismo gate sirve para comentar un PR/issue y para etiquetar un issue sin conocer la
acción concreta. Garantía estructural: a la cola real SOLO llega lo aprobado.
"""

from __future__ import annotations

import json

from arq.connections import ArqRedis

# Prefijo de las claves de la sala de espera en Redis (pedidos sin aprobar aún).
PENDING_KEY_PREFIX = "pending-approval:"


def _pending_key(approval_id: str) -> str:
    return f"{PENDING_KEY_PREFIX}{approval_id}"


async def enqueue_pending(pool: ArqRedis, *, approval_id: str, task: str, data: dict) -> str:
    """Guarda el pedido en la sala de espera. Devuelve el approval_id.

    `task` es el nombre de la task de arq a encolar si se aprueba; `data`, su payload.
    """
    payload = json.dumps({"task": task, "data": data})
    # nx=True: solo crea la clave si NO existe; un pedido idéntico no se duplica.
    await pool.set(_pending_key(approval_id), payload, nx=True)
    return approval_id


async def approve(pool: ArqRedis, approval_id: str) -> str | None:
    """El humano aprobó: mueve el pedido de la sala de espera a la cola real.

    Devuelve el nombre de la task encolada, o None si el pedido ya no existe
    (expirado o ya resuelto).
    """
    raw = await pool.get(_pending_key(approval_id))
    if raw is None:
        return None

    entry = json.loads(raw)
    # Mismo _job_id que el approval_id -> la idempotencia se mantiene en ejecución:
    # si por alguna razón se aprueba dos veces, arq no encola el job duplicado.
    await pool.enqueue_job(entry["task"], entry["data"], _job_id=approval_id)
    await pool.delete(_pending_key(approval_id))
    return entry["task"]


async def reject(pool: ArqRedis, approval_id: str) -> bool:
    """El humano rechazó: borra el pedido. Nunca llega al worker.

    Devuelve False si el pedido ya no existía.
    """
    deleted = await pool.delete(_pending_key(approval_id))
    return deleted > 0
