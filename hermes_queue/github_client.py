"""Cliente mínimo para postear un comentario en un PR de GitHub.

Un PR es, para la API, un issue con código: el comentario de conversación se crea
con el endpoint de issues. El PAT se lee de GITHUB_PAT (~/.hermes/.env), nunca
hardcodeado, y está scopeado a read + comment (sin merge/push).
"""

from __future__ import annotations

import os

import httpx

# Versión de la API de GitHub. 2022-11-28 es el default estable y soportado.
# (La última es 2026-03-10; se puede bumpear si hiciera falta.)
GITHUB_API_VERSION = "2022-11-28"


async def post_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Postea un comentario en el PR y devuelve la URL del comentario creado.

    Lanza httpx.HTTPStatusError si GitHub responde con error (4xx/5xx) y
    httpx.RequestError ante problemas de red/timeout.
    """
    token = os.environ.get("GITHUB_PAT")
    if not token:
        raise RuntimeError("Falta GITHUB_PAT en el entorno (~/.hermes/.env).")

    # PR number = issue number en este endpoint.
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json={"body": body})

    response.raise_for_status()
    return response.json()["html_url"]
