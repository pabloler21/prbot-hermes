"""Tipo de dato e idempotencia del pedido "comentar en un PR/issue de GitHub".

El approval gate (encolar pendiente, aprobar, rechazar) es genérico y vive en
jobs/gate.py. Acá solo definimos la forma del pedido y su clave de idempotencia.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Nombre de la task que ejecuta el worker. Debe coincidir EXACTO con el nombre de
# la función registrada en WorkerSettings.functions (en el worker).
POST_COMMENT_TASK = "post_comment"


@dataclass
class PostCommentRequest:
    """Datos de un pedido de comentar en un PR/issue de GitHub."""

    repo: str  # "owner/repo"; se valida contra la allowlist en el worker
    pr_number: int  # número del Pull Request o issue (mismo endpoint)
    body: str  # texto del comentario


def idempotency_key(req: PostCommentRequest) -> str:
    """Huella sha256 (hex) del contenido. Mismo contenido -> mismo id -> no duplica."""
    raw = f"{req.repo}#{req.pr_number}:{req.body}".encode()
    return hashlib.sha256(raw).hexdigest()
