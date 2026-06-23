"""Cliente mínimo para actuar sobre issues/PRs de GitHub.

Un PR es, para la API, un issue con código: tanto el comentario de conversación
como las labels se manejan con los endpoints de issues. El PAT se lee de
GITHUB_PAT (~/.hermes/.env), nunca hardcodeado, y está scopeado a read + comentar
+ etiquetar (Issues/PR write), sin merge/push.
"""

from __future__ import annotations

import os

import httpx

# Versión de la API de GitHub. 2022-11-28 es el default estable y soportado.
# (La última es 2026-03-10; se puede bumpear si hiciera falta.)
GITHUB_API_VERSION = "2022-11-28"


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
