"""Cliente mínimo para actuar sobre issues/PRs de GitHub.

Un PR es, para la API, un issue con código: tanto el comentario de conversación
como las labels se manejan con los endpoints de issues. El PAT se lee de
GITHUB_PAT (~/.hermes/.env), nunca hardcodeado, y está scopeado a read + comentar
+ etiquetar (Issues/PR write), sin merge/push.
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

# Versión de la API de GitHub. 2022-11-28 es el default estable y soportado.
# (La última es 2026-03-10; se puede bumpear si hiciera falta.)
GITHUB_API_VERSION = "2022-11-28"


def _parse_iso(value: str) -> datetime:
    """Parsea un timestamp ISO 8601 de GitHub (sufijo Z = UTC) a datetime aware."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _headers() -> dict[str, str]:
    """Headers comunes con el PAT. Lanza si falta el token."""
    token = os.environ.get("GITHUB_PAT")
    if not token:
        raise RuntimeError("Falta GITHUB_PAT en el entorno (~/.hermes/.env).")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


async def post_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Postea un comentario en un PR o issue y devuelve la URL del comentario.

    El endpoint de comentarios de issues sirve igual para PRs (un PR es un issue).
    Lanza httpx.HTTPStatusError si GitHub responde con error (4xx/5xx) y
    httpx.RequestError ante problemas de red/timeout.
    """
    # PR number = issue number en este endpoint.
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=_headers(), json={"body": body})

    response.raise_for_status()
    return response.json()["html_url"]


async def add_issue_labels(repo: str, issue_number: int, labels: list[str]) -> str:
    """Agrega labels a un issue (o PR) y devuelve la URL del issue etiquetado.

    Endpoint POST /issues/{n}/labels (verificado en docs.github.com, 2026-06-23):
    agrega las labels a las ya existentes, no las reemplaza. Requiere PAT con
    Issues: write o Pull requests: write.

    Lanza httpx.HTTPStatusError (4xx/5xx) y httpx.RequestError (red/timeout).
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=_headers(), json={"labels": labels})

    response.raise_for_status()
    # El endpoint de labels devuelve la lista de labels, no el issue. Construimos
    # la URL del issue para reportarla de vuelta en Discord.
    return f"https://github.com/{repo}/issues/{issue_number}"


async def list_open_pull_requests(repo: str) -> list[dict]:
    """Lista los PRs ABIERTOS (excluye drafts) de un repo, para el digest.

    Endpoint GET /repos/{repo}/pulls?state=open. Devuelve, por cada PR, solo lo que
    el digest necesita: number, title, author, created_at (ISO 8601), html_url.

    Lanza httpx.HTTPStatusError (4xx/5xx) y httpx.RequestError (red/timeout).
    """
    url = f"https://api.github.com/repos/{repo}/pulls"
    # sort/direction: los más viejos primero (los que más tiempo llevan esperando review).
    params = {"state": "open", "per_page": 100, "sort": "created", "direction": "asc"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(), params=params)

    response.raise_for_status()
    prs: list[dict] = []
    for pr in response.json():
        if pr.get("draft"):
            continue  # los borradores no necesitan review todavía
        prs.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
                "html_url": pr["html_url"],
            }
        )
    return prs


async def _get_repo(repo: str, endpoint: str, params: dict) -> list[dict]:
    """GET genérico a /repos/{repo}/{endpoint} con los headers/PAT. Devuelve el JSON."""
    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=_headers(), params=params)
    response.raise_for_status()
    return response.json()


async def list_recently_merged_prs(repo: str, since: datetime) -> list[dict]:
    """PRs MERGEADOS desde `since`. Incluye base_ref para poder filtrar por rama (p. ej. main).

    /pulls?state=closed trae cerrados y mergeados; nos quedamos solo con los que tienen
    merged_at y >= since. Devuelve number, title, author, merged_at, base_ref, html_url.
    """
    data = await _get_repo(
        repo, "pulls", {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100}
    )
    out: list[dict] = []
    for pr in data:
        merged_at = pr.get("merged_at")
        if not merged_at or _parse_iso(merged_at) < since:
            continue  # cerrado sin mergear, o mergeado antes de la ventana
        out.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "merged_at": merged_at,
                "base_ref": pr["base"]["ref"],
                "html_url": pr["html_url"],
            }
        )
    return out


async def list_recently_closed_issues(repo: str, since: datetime) -> list[dict]:
    """Issues (NO PRs) cerrados desde `since`. Para el resumen semanal.

    El endpoint /issues incluye PRs (un PR es un issue); los excluimos por la clave
    'pull_request'. Devuelve number, title, author, closed_at, html_url.
    """
    data = await _get_repo(
        repo,
        "issues",
        {
            "state": "closed",
            "since": since.isoformat(),
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
        },
    )
    out: list[dict] = []
    for it in data:
        if "pull_request" in it:
            continue  # es un PR, no un issue
        closed_at = it.get("closed_at")
        if not closed_at or _parse_iso(closed_at) < since:
            continue
        out.append(
            {
                "number": it["number"],
                "title": it["title"],
                "author": it["user"]["login"],
                "closed_at": closed_at,
                "html_url": it["html_url"],
            }
        )
    return out


async def list_new_issues(repo: str, since: datetime) -> list[dict]:
    """Issues (NO PRs) ABIERTOS creados DESPUÉS de `since`. Para el alert de issues nuevos.

    Trae los más recientes por fecha de creación y corta al pasar el cursor. Excluye PRs.
    Devuelve number, title, author, created_at, labels, html_url.
    """
    data = await _get_repo(
        repo,
        "issues",
        {"state": "open", "sort": "created", "direction": "desc", "per_page": 50},
    )
    out: list[dict] = []
    for it in data:
        if "pull_request" in it:
            continue
        if _parse_iso(it["created_at"]) <= since:
            break  # ordenados por creación desc: de acá para abajo, todos son viejos
        out.append(
            {
                "number": it["number"],
                "title": it["title"],
                "author": it["user"]["login"],
                "created_at": it["created_at"],
                "labels": [lbl["name"] for lbl in it.get("labels", [])],
                "html_url": it["html_url"],
            }
        )
    return out
