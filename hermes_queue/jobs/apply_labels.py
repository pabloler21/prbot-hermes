"""Tipo de dato e idempotencia del pedido "etiquetar un issue de GitHub".

Espeja a jobs/post_comment.py: el approval gate genérico (jobs/gate.py) y el
dead-letter sirven igual para esta acción. Acá solo la forma del pedido y su
clave de idempotencia.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Nombre de la task que ejecuta el worker. Debe coincidir EXACTO con la función
# registrada en WorkerSettings.functions.
APPLY_LABELS_TASK = "apply_issue_labels"


@dataclass
class ApplyLabelsRequest:
    """Datos de un pedido de aplicar labels a un issue de GitHub."""

    repo: str  # "owner/repo"; se valida contra la allowlist en el worker
    issue_number: int  # número del issue
    labels: list[str]  # labels a agregar (se suman a las existentes)


def idempotency_key(req: ApplyLabelsRequest) -> str:
    """Huella sha256 (hex) del contenido. Mismo set de labels -> mismo id -> no duplica."""
    # Ordenamos las labels para que el mismo conjunto en distinto orden no genere ids
    # distintos (etiquetar es idempotente por naturaleza).
    labels = ",".join(sorted(req.labels))
    raw = f"{req.repo}#{req.issue_number}:{labels}".encode()
    return hashlib.sha256(raw).hexdigest()
