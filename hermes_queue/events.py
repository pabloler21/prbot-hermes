"""Eventos pub/sub sobre Redis para coordinar los procesos del flujo.

El servidor MCP (donde Hermes propone) y el bot de aprobación de Discord corren
en procesos SEPARADOS. Se comunican por un canal pub/sub de Redis: cuando se
encola un pedido pendiente, se publica un aviso que el bot escucha para mostrar
los botones de aprobación.

El aviso lleva un `summary` ya formateado (texto a mostrar) y un `kind` (la
acción): así el bot es agnóstico de la acción concreta y no conoce sus campos.
"""

from __future__ import annotations

import json

from arq.connections import ArqRedis

# Canal pub/sub donde se anuncian los pedidos pendientes de aprobación.
PENDING_CHANNEL = "hermes:pending"


async def publish_pending(pool: ArqRedis, *, approval_id: str, kind: str, summary: str) -> None:
    """Anuncia un pedido pendiente para que el bot de aprobación lo muestre.

    `kind` identifica la acción (p. ej. "comment", "labels"); `summary` es el
    texto ya formateado que el bot muestra junto a los botones ✅/❌.
    """
    payload = json.dumps(
        {
            "approval_id": approval_id,
            "kind": kind,
            "summary": summary,
        }
    )
    # publish() viene de redis-py (ArqRedis lo hereda): manda el mensaje a todos
    # los suscriptores del canal (el bot de aprobación).
    await pool.publish(PENDING_CHANNEL, payload)
