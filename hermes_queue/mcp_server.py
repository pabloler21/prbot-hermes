"""MCP server que le da a Hermes la herramienta para PROPONER un comentario en un PR.

Hermes (el LLM) llama a `propose_pr_comment`; esto NO postea nada: encola un pedido
PENDIENTE de aprobación y avisa al bot de Discord por pub/sub. Recién tras la
aprobación humana el worker postea. Es el lado "productor" del approval gate.

Se registra en Hermes (en el VPS) con algo como:
    hermes mcp add hermes-queue --command uv \
      --env REDIS_URL='${REDIS_URL}' \
      --args run python -m hermes_queue.mcp_server
"""

from __future__ import annotations

from arq import create_pool
from mcp.server.fastmcp import FastMCP

from hermes_queue.events import publish_pending
from hermes_queue.jobs.post_comment import PostCommentRequest, enqueue_pending
from hermes_queue.settings import redis_settings_from_env

mcp = FastMCP("hermes-queue")


@mcp.tool()
async def propose_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Propone postear un comentario en un Pull Request de GitHub.

    NO postea directamente: encola el pedido en estado pendiente y un humano debe
    aprobarlo por Discord (botones ✅/❌). Usar cuando el usuario pide comentar,
    responder o dejar una nota en un PR.

    Args:
        repo: Repositorio en formato "owner/repo".
        pr_number: Número del Pull Request.
        body: Texto del comentario (Markdown permitido).

    Returns:
        Mensaje confirmando que el pedido quedó pendiente de aprobación.
    """
    pool = await create_pool(redis_settings_from_env())
    try:
        req = PostCommentRequest(repo=repo, pr_number=pr_number, body=body)
        approval_id = await enqueue_pending(pool, req)
        await publish_pending(pool, approval_id, repo, pr_number, body)
    finally:
        # Cerramos la conexión que abrimos para esta llamada.
        await pool.aclose()

    return (
        f"Pedido de comentario encolado en {repo}#{pr_number}. "
        f"Pendiente de aprobación por Discord (id: {approval_id[:12]}…)."
    )


def main() -> None:
    """Punto de entrada: corre el server MCP por stdio (lo spawnea Hermes)."""
    mcp.run()


if __name__ == "__main__":
    main()
