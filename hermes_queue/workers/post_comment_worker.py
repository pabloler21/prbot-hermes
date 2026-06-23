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

from hermes_queue.deadletter import record_dead_letter
from hermes_queue.github_client import post_pr_comment
from hermes_queue.guardrails import is_repo_allowed
from hermes_queue.jobs.post_comment import PostCommentRequest
from hermes_queue.settings import redis_settings_from_env

logger = logging.getLogger("hermes_queue.post_comment")

# Máximo de intentos por job (coincide con WorkerSettings.max_tries). Lo definimos como
# constante para poder detectar dentro de la task cuándo estamos en el último intento.
MAX_TRIES = 5


async def post_comment(ctx: dict, data: dict) -> str | None:
    """Task que postea un comentario aprobado.

    ctx lo provee arq (incluye 'job_try', el número de intento). data es el
    pedido serializado que encolamos al aprobar.
    """
    req = PostCommentRequest(**data)

    # 1) Guardrail: allowlist. Si el repo no está permitido, NO reintentamos
    #    (nunca va a estarlo): lo mandamos al dead-letter y salimos. Defensa en profundidad.
    if not is_repo_allowed(req.repo):
        logger.error("Repo fuera de la allowlist, rechazado: %s", req.repo)
        await record_dead_letter(ctx["redis"], reason="repo-not-allowed", data=data)
        return None

    # 2) Postear en GitHub, distinguiendo errores transitorios de permanentes.
    try:
        comment_url = await post_pr_comment(req.repo, req.pr_number, req.body)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status >= 500:
            # 5xx = problema transitorio de GitHub -> reintentar (o DLQ si se agotó).
            return await _retry_or_dead_letter(ctx, data, reason=f"github-{status}", exc=exc)
        # 4xx = error permanente (auth, PR inexistente...) -> no reintentar, va al DLQ.
        logger.error(
            "GitHub rechazó el comentario (%s) en %s#%s",
            status,
            req.repo,
            req.pr_number,
        )
        await record_dead_letter(ctx["redis"], reason=f"github-{status}", data=data)
        return None
    except httpx.RequestError as exc:
        # Red caída / timeout = transitorio -> reintentar (o DLQ si se agotó).
        return await _retry_or_dead_letter(ctx, data, reason="network-error", exc=exc)

    logger.info("Comentario posteado en %s#%s: %s", req.repo, req.pr_number, comment_url)
    return comment_url


async def _retry_or_dead_letter(ctx: dict, data: dict, *, reason: str, exc: Exception) -> None:
    """Reintenta un fallo transitorio con backoff; si ya se agotaron los intentos, lo
    manda al dead-letter para que no se pierda silenciosamente.

    `raise Retry` en el último intento no salva el payload: arq lo registra como fallido
    y lo descarta. Por eso, cuando estamos en el último try, lo guardamos nosotros.
    """
    if ctx["job_try"] >= MAX_TRIES:
        logger.error("Reintentos agotados (%s) -> dead-letter: %s", reason, data)
        await record_dead_letter(ctx["redis"], reason=f"{reason}-retries-exhausted", data=data)
        return None
    # Backoff lineal: 5s, 10s, 15s... según el número de intento.
    raise Retry(defer=ctx["job_try"] * 5) from exc


class WorkerSettings:
    """Configuración que arq lee para arrancar el worker."""

    functions = [post_comment]
    redis_settings = redis_settings_from_env()
    max_tries = MAX_TRIES
    # Cap de concurrencia = "rate limiting" en arq (no tiene token-bucket por QPS). El
    # approval gate humano ya throttlea las escrituras; este cap es defensa en profundidad
    # contra que el agente 24/7 alguna vez haga burst contra la API de GitHub. Ver ADR-0007.
    max_jobs = 2
