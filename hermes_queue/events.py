"""Eventos pub/sub sobre Redis para coordinar los procesos del flujo.

El servidor MCP (donde Hermes propone) y el bot de aprobación de Discord corren
en procesos SEPARADOS. Se comunican por un canal pub/sub de Redis: cuando se
encola un pedido pendiente, se publica un aviso que el bot escucha para mostrar
los botones de aprobación.
"""

from __future__ import annotations

import json

from arq.connections import ArqRedis

# Canal pub/sub donde se anuncian los pedidos pendientes de aprobación.
PENDING_CHANNEL = "hermes:pending"


async def publish_pending(
    pool: ArqRedis,
    approval_id: str,
    repo: str,
    pr_number: int,
    body: str,
) -> None:
    """Anuncia un pedido pendiente para que el bot de aprobación lo muestre."""
    payload = json.dumps(
        {
            "approval_id": approval_id,
            "repo": repo,
            "pr_number": pr_number,
            "body": body,
        }
    )
    # publish() viene de redis-py (ArqRedis lo hereda): manda el mensaje a todos
    # los suscriptores del canal (el bot de aprobación).
    await pool.publish(PENDING_CHANNEL, payload)
