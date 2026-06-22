"""Worker de arq: ejecuta los pedidos APROBADOS de comentar en un PR.

Responsabilidades:
  1. Validar la allowlist de repos (guardrail determinístico).
  2. Postear el comentario en GitHub.

Solo se llega acá tras la aprobación humana por Discord (ver jobs/post_comment.py,
Enfoque B): la cola de arq estructuralmente solo contiene trabajo aprobado.

Correr el worker:
    uv run arq hermes_queue.workers.post_comment_worker.WorkerSettings
"""

from __future__ import annotations

import logging

import httpx
from arq import Retry

from hermes_queue.github_client import post_pr_comment
from hermes_queue.guardrails import is_repo_allowed
from hermes_queue.jobs.post_comment import PostCommentRequest
from hermes_queue.settings import redis_settings_from_env

logger = logging.getLogger("hermes_queue.post_comment")


async def post_comment(ctx: dict, data: dict) -> str | None:
    """Task que postea un comentario aprobado.

    ctx lo provee arq (incluye 'job_try', el número de intento). data es el
    pedido serializado que encolamos al aprobar.
    """
    req = PostCommentRequest(**data)

    # 1) Guardrail: allowlist. Si el repo no está permitido, NO reintentamos
    #    (nunca va a estarlo): logueamos y salimos. Defensa en profundidad.
    if not is_repo_allowed(req.repo):
        logger.error("Repo fuera de la allowlist, rechazado: %s", req.repo)
        return None

    # 2) Postear en GitHub, distinguiendo errores transitorios de permanentes.
    try:
        comment_url = await post_pr_comment(req.repo, req.pr_number, req.body)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status >= 500:
            # 5xx = problema transitorio de GitHub -> reintentar con backoff.
            raise Retry(defer=ctx["job_try"] * 5) from exc
        # 4xx = error permanente (auth, PR inexistente...) -> no reintentar.
        logger.error(
            "GitHub rechazó el comentario (%s) en %s#%s",
            status,
            req.repo,
            req.pr_number,
        )
        return None
    except httpx.RequestError as exc:
        # Red caída / timeout = transitorio -> reintentar con backoff.
        raise Retry(defer=ctx["job_try"] * 5) from exc

    logger.info("Comentario posteado en %s#%s: %s", req.repo, req.pr_number, comment_url)
    return comment_url


class WorkerSettings:
    """Configuración que arq lee para arrancar el worker."""

    functions = [post_comment]
    redis_settings = redis_settings_from_env()
    # max_tries de arq por defecto es 5; coincide con nuestra intención de reintentos.
