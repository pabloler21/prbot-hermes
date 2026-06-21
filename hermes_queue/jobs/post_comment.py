"""Approval gate (Enfoque B) del flujo "comentar en un PR de GitHub".

Tres operaciones:
  1. enqueue_pending -> guarda el pedido en la SALA DE ESPERA (una clave de Redis).
  2. approve         -> el humano dijo "sí"; lo mueve a la cola real de arq.
  3. reject          -> el humano dijo "no"; lo borra. Nunca llega al worker.

Garantía estructural: a la cola real (la que consume el worker) SOLO llega lo
aprobado. La sala de espera es solo almacenamiento; nadie la ejecuta.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from arq.connections import ArqRedis

# Prefijo de las claves de la sala de espera en Redis (pedidos sin aprobar aún).
PENDING_KEY_PREFIX = "pending-approval:"

# Nombre de la task que ejecuta el worker. Debe coincidir EXACTO con el nombre de
# la función registrada en WorkerSettings.functions (en el worker).
POST_COMMENT_TASK = "post_comment"


@dataclass
class PostCommentRequest:
    """Datos de un pedido de comentar en un PR de GitHub."""

    repo: str  # "owner/repo"; se valida contra la allowlist en el worker
    pr_number: int  # número del Pull Request
    body: str  # texto del comentario


def idempotency_key(req: PostCommentRequest) -> str:
    """Huella sha256 (hex) del contenido. Mismo contenido -> mismo id -> no duplica."""
    raw = f"{req.repo}#{req.pr_number}:{req.body}".encode()
    return hashlib.sha256(raw).hexdigest()


def _pending_key(approval_id: str) -> str:
    return f"{PENDING_KEY_PREFIX}{approval_id}"


async def enqueue_pending(pool: ArqRedis, req: PostCommentRequest) -> str:
    """Guarda el pedido en la sala de espera. Devuelve el approval_id."""
    approval_id = idempotency_key(req)
    # nx=True: solo crea la clave si NO existe; un pedido idéntico no se duplica.
    await pool.set(_pending_key(approval_id), json.dumps(asdict(req)), nx=True)
    return approval_id


async def approve(pool: ArqRedis, approval_id: str) -> bool:
    """El humano aprobó: mueve el pedido de la sala de espera a la cola real.

    Devuelve False si el pedido ya no existe (expirado o ya resuelto).
    """
    raw = await pool.get(_pending_key(approval_id))
    if raw is None:
        return False

    data = json.loads(raw)
    # Mismo _job_id que el approval_id -> la idempotencia se mantiene en ejecución:
    # si por alguna razón se aprueba dos veces, arq no encola el job duplicado.
    await pool.enqueue_job(POST_COMMENT_TASK, data, _job_id=approval_id)
    await pool.delete(_pending_key(approval_id))
    return True


async def reject(pool: ArqRedis, approval_id: str) -> bool:
    """El humano rechazó: borra el pedido. Nunca llega al worker.

    Devuelve False si el pedido ya no existía.
    """
    deleted = await pool.delete(_pending_key(approval_id))
    return deleted > 0
