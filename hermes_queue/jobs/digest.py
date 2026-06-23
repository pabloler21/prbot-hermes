"""Construye el texto del Daily PR Digest (PRs abiertos esperando review).

Lógica determinística y casi pura: pide los PRs al github_client, calcula la
antigüedad de cada uno y formatea Markdown para Discord. NO habla con Redis ni con
Discord (eso lo hacen el worker y el discord_client). Separar "qué decir" de "cómo
entregarlo" hace esta lógica fácil de testear sin infraestructura.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hermes_queue.github_client import list_open_pull_requests


def _days_open(created_at: str, now: datetime) -> int:
    """Días enteros desde que se abrió el PR (created_at viene en ISO 8601)."""
    # GitHub usa sufijo "Z" (UTC); fromisoformat lo entiende como "+00:00".
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return (now - created).days


def _format_age(dias: int) -> str:
    """'hoy', '1 día' o 'N días' según la antigüedad."""
    if dias <= 0:
        return "hoy"
    return f"{dias} día" if dias == 1 else f"{dias} días"


async def build_pr_digest(repos: list[str], now: datetime | None = None) -> str:
    """Arma el Markdown del digest de PRs abiertos para los repos dados.

    `now` es inyectable para tests; por defecto, el momento actual en UTC.
    """
    now = now or datetime.now(UTC)
    lineas = [f"📋 **Daily PR Digest** · {now:%Y-%m-%d}"]

    for repo in repos:
        prs = await list_open_pull_requests(repo)
        lineas.append(f"\n**{repo}** — {len(prs)} PR(s) abiertos esperando review:")
        if not prs:
            lineas.append("✅ No hay PRs abiertos.")
            continue
        for pr in prs:
            antig = _format_age(_days_open(pr["created_at"], now))
            lineas.append(
                f"• #{pr['number']} {pr['title']} — @{pr['author']} — {antig} — {pr['html_url']}"
            )

    return "\n".join(lineas)
