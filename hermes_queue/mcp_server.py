"""MCP server con las herramientas para que Hermes PROPONGA acciones sobre GitHub.

Hermes (el LLM) llama a una tool; esto NO actúa sobre GitHub: encola un pedido
PENDIENTE de aprobación y avisa al bot de Discord por pub/sub. Recién tras la
aprobación humana el worker ejecuta. Es el lado "productor" del approval gate.

Las tools comparten el gate genérico (jobs/gate.py): cada una arma su payload,
su clave de idempotencia y un resumen para el bot.

Se registra en Hermes (en el VPS) con algo como:
    hermes mcp add hermes-queue --command uv \
      --env REDIS_URL='${REDIS_URL}' \
      --args run python -m hermes_queue.mcp_server
"""

from __future__ import annotations

from dataclasses import asdict

from arq import create_pool
from mcp.server.fastmcp import FastMCP

from hermes_queue.events import publish_pending
from hermes_queue.jobs.apply_labels import (
    APPLY_LABELS_TASK,
    ApplyLabelsRequest,
)
from hermes_queue.jobs.apply_labels import (
    idempotency_key as labels_idempotency_key,
)
from hermes_queue.jobs.gate import enqueue_pending
from hermes_queue.jobs.post_comment import (
    POST_COMMENT_TASK,
    PostCommentRequest,
)
from hermes_queue.jobs.post_comment import (
    idempotency_key as comment_idempotency_key,
)
from hermes_queue.settings import redis_settings_from_env

mcp = FastMCP("hermes-queue")


@mcp.tool()
async def propose_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Propone postear un comentario en un Pull Request o issue de GitHub.

    NO postea directamente: encola el pedido en estado pendiente y un humano debe
    aprobarlo por Discord (botones ✅/❌). Usar cuando el usuario pide comentar,
    responder o dejar una nota en un PR o issue (el mismo endpoint sirve para ambos).

    Args:
        repo: Repositorio en formato "owner/repo".
        pr_number: Número del Pull Request o issue.
        body: Texto del comentario (Markdown permitido).

    Returns:
        Mensaje confirmando que el pedido quedó pendiente de aprobación.
    """
    req = PostCommentRequest(repo=repo, pr_number=pr_number, body=body)
    approval_id = comment_idempotency_key(req)
    summary = f"**Comentar** en `{repo}` · #{pr_number}\n> {body}\n\n¿Aprobar?"

    pool = await create_pool(redis_settings_from_env())
    try:
        await enqueue_pending(
            pool, approval_id=approval_id, task=POST_COMMENT_TASK, data=asdict(req)
        )
        await publish_pending(pool, approval_id=approval_id, kind="comment", summary=summary)
    finally:
        await pool.aclose()

    return (
        f"Pedido de comentario encolado en {repo}#{pr_number}. "
        f"Pendiente de aprobación por Discord (id: {approval_id[:12]}…)."
    )


@mcp.tool()
async def propose_issue_labels(repo: str, issue_number: int, labels: list[str]) -> str:
    """Propone aplicar labels (etiquetas) a un issue de GitHub.

    NO etiqueta directamente: encola el pedido en estado pendiente y un humano debe
    aprobarlo por Discord (botones ✅/❌). Usar al hacer triage de un issue para
    proponer labels de tipo/prioridad (p. ej. "bug", "priority:high"). Las labels se
    suman a las ya existentes.

    Args:
        repo: Repositorio en formato "owner/repo".
        issue_number: Número del issue.
        labels: Lista de labels a agregar.

    Returns:
        Mensaje confirmando que el pedido quedó pendiente de aprobación.
    """
    req = ApplyLabelsRequest(repo=repo, issue_number=issue_number, labels=labels)
    approval_id = labels_idempotency_key(req)
    summary = (
        f"**Etiquetar** `{repo}` · issue #{issue_number}\n"
        f"> labels: {', '.join(labels)}\n\n¿Aprobar?"
    )

    pool = await create_pool(redis_settings_from_env())
    try:
        await enqueue_pending(
            pool, approval_id=approval_id, task=APPLY_LABELS_TASK, data=asdict(req)
        )
        await publish_pending(pool, approval_id=approval_id, kind="labels", summary=summary)
    finally:
        await pool.aclose()

    return (
        f"Pedido de labels encolado en {repo}#{issue_number} ({', '.join(labels)}). "
        f"Pendiente de aprobación por Discord (id: {approval_id[:12]}…)."
    )


def main() -> None:
    """Punto de entrada: corre el server MCP por stdio (lo spawnea Hermes)."""
    mcp.run()


if __name__ == "__main__":
    main()
