"""Worker de arq: ejecuta acciones APROBADAS sobre GitHub + trabajo recurrente.

Tasks (encoladas tras aprobación humana — ver jobs/gate.py, Enfoque B):
  - post_comment       -> postea un comentario en un PR/issue.
  - apply_issue_labels -> aplica labels a un issue (triage de la Fase 5).

Cron jobs (recurrentes, sin approval gate — solo leen GitHub y publican en NUESTRO Discord):
  - daily_pr_digest    -> resumen diario de PRs abiertos, posteado por webhook (Fase 6).

Cada task de escritura: 1) valida la allowlist de repos (guardrail determinístico),
2) ejecuta contra GitHub, 3) ante fallo permanente o reintentos agotados, va al dead-letter.

Correr el worker:
    uv run arq hermes_queue.workers.post_comment_worker.WorkerSettings
"""

from __future__ import annotations

import logging
from datetime import timedelta, timezone

import httpx
from arq import Retry, cron

from hermes_queue.deadletter import record_dead_letter
from hermes_queue.discord_client import post_to_discord
from hermes_queue.github_client import add_issue_labels, post_pr_comment
from hermes_queue.guardrails import allowed_repos, is_repo_allowed
from hermes_queue.jobs.apply_labels import APPLY_LABELS_TASK, ApplyLabelsRequest
from hermes_queue.jobs.digest import build_pr_digest
from hermes_queue.jobs.post_comment import POST_COMMENT_TASK, PostCommentRequest
from hermes_queue.settings import redis_settings_from_env

logger = logging.getLogger("hermes_queue.worker")

# Máximo de intentos por job (coincide con WorkerSettings.max_tries). Lo definimos como
# constante para poder detectar dentro de la task cuándo estamos en el último intento.
MAX_TRIES = 5

# Zona horaria del scheduling de cron. Explícita (el plan lo exige): UTC-3 (Argentina,
# sin DST). Sin esto, "las 9" serían ambiguas (¿de qué huso?).
TIMEZONE = timezone(timedelta(hours=-3))


async def post_comment(ctx: dict, data: dict) -> str | None:
    """Task que postea un comentario aprobado en un PR/issue.

    ctx lo provee arq (incluye 'job_try', el número de intento). data es el
    pedido serializado que encolamos al aprobar.
    """
    req = PostCommentRequest(**data)

    # 1) Guardrail: allowlist. Si el repo no está permitido, NO reintentamos
    #    (nunca va a estarlo): lo mandamos al dead-letter y salimos. Defensa en profundidad.
    if not is_repo_allowed(req.repo):
        logger.error("Repo fuera de la allowlist, rechazado: %s", req.repo)
        await record_dead_letter(
            ctx["redis"], task=POST_COMMENT_TASK, reason="repo-not-allowed", data=data
        )
        return None

    # 2) Postear en GitHub, distinguiendo errores transitorios de permanentes.
    try:
        comment_url = await post_pr_comment(req.repo, req.pr_number, req.body)
    except httpx.HTTPStatusError as exc:
        return await _handle_http_error(
            ctx, data, task=POST_COMMENT_TASK, exc=exc, ref=f"{req.repo}#{req.pr_number}"
        )
    except httpx.RequestError as exc:
        return await _retry_or_dead_letter(
            ctx, data, task=POST_COMMENT_TASK, reason="network-error", exc=exc
        )

    logger.info("Comentario posteado en %s#%s: %s", req.repo, req.pr_number, comment_url)
    return comment_url


async def apply_issue_labels(ctx: dict, data: dict) -> str | None:
    """Task que aplica labels aprobadas a un issue (triage de la Fase 5).

    Misma estructura que post_comment: allowlist -> GitHub -> dead-letter ante fallo.
    """
    req = ApplyLabelsRequest(**data)

    if not is_repo_allowed(req.repo):
        logger.error("Repo fuera de la allowlist, rechazado: %s", req.repo)
        await record_dead_letter(
            ctx["redis"], task=APPLY_LABELS_TASK, reason="repo-not-allowed", data=data
        )
        return None

    try:
        issue_url = await add_issue_labels(req.repo, req.issue_number, req.labels)
    except httpx.HTTPStatusError as exc:
        return await _handle_http_error(
            ctx, data, task=APPLY_LABELS_TASK, exc=exc, ref=f"{req.repo}#{req.issue_number}"
        )
    except httpx.RequestError as exc:
        return await _retry_or_dead_letter(
            ctx, data, task=APPLY_LABELS_TASK, reason="network-error", exc=exc
        )

    logger.info("Labels aplicadas en %s#%s: %s", req.repo, req.issue_number, req.labels)
    return issue_url


async def _handle_http_error(
    ctx: dict, data: dict, *, task: str, exc: httpx.HTTPStatusError, ref: str
) -> None:
    """Decide qué hacer ante un error HTTP de GitHub: 5xx reintenta, 4xx al dead-letter."""
    status = exc.response.status_code
    if status >= 500:
        # 5xx = problema transitorio de GitHub -> reintentar (o DLQ si se agotó).
        return await _retry_or_dead_letter(ctx, data, task=task, reason=f"github-{status}", exc=exc)
    # 4xx = error permanente (auth, recurso inexistente...) -> no reintentar, al DLQ.
    logger.error("GitHub rechazó la acción (%s) en %s", status, ref)
    await record_dead_letter(ctx["redis"], task=task, reason=f"github-{status}", data=data)
    return None


async def _retry_or_dead_letter(
    ctx: dict, data: dict, *, task: str, reason: str, exc: Exception
) -> None:
    """Reintenta un fallo transitorio con backoff; si ya se agotaron los intentos, lo
    manda al dead-letter para que no se pierda silenciosamente.

    `raise Retry` en el último intento no salva el payload: arq lo registra como fallido
    y lo descarta. Por eso, cuando estamos en el último try, lo guardamos nosotros.
    """
    if ctx["job_try"] >= MAX_TRIES:
        logger.error("Reintentos agotados (%s) -> dead-letter: %s", reason, data)
        await record_dead_letter(
            ctx["redis"], task=task, reason=f"{reason}-retries-exhausted", data=data
        )
        return None
    # Backoff lineal: 5s, 10s, 15s... según el número de intento.
    raise Retry(defer=ctx["job_try"] * 5) from exc


async def daily_pr_digest(ctx: dict) -> str:
    """Cron job: arma el resumen de PRs abiertos y lo postea a Discord (webhook).

    Determinístico y SIN approval gate: solo lee GitHub y publica en nuestro propio
    canal de Discord (no escribe en GitHub), así que no necesita aprobación humana.
    Itera sobre los repos de la allowlist (misma fuente determinística que las escrituras).
    """
    repos = allowed_repos()
    texto = await build_pr_digest(repos)
    await post_to_discord(texto)
    logger.info("Daily PR digest posteado (%d repos)", len(repos))
    return texto


class WorkerSettings:
    """Configuración que arq lee para arrancar el worker."""

    functions = [post_comment, apply_issue_labels]
    # Trabajo recurrente. `unique=True` es el default de arq: el job_id del cron es
    # "<nombre>:<hora_programada>", así un reinicio cerca de las 9:00 NO duplica el envío.
    cron_jobs = [
        cron(daily_pr_digest, weekday={0, 1, 2, 3, 4}, hour=9, minute=0),  # lun-vie 09:00
    ]
    timezone = TIMEZONE
    redis_settings = redis_settings_from_env()
    max_tries = MAX_TRIES
    # Cap de concurrencia = "rate limiting" en arq (no tiene token-bucket por QPS). El
    # approval gate humano ya throttlea las escrituras; este cap es defensa en profundidad
    # contra que el agente 24/7 alguna vez haga burst contra la API de GitHub. Ver ADR-0007.
    max_jobs = 2
