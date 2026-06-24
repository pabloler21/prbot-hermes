"""Reportes deterministas por cron: Stale PR Alert y Weekly Summary (Fase 6b).

Son "foto del estado actual" (no necesitan cursor): consultan GitHub y formatean Markdown.
Espejan a jobs/digest.py. La orquestación (cuándo correr, postear) la hace el worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hermes_queue.github_client import (
    list_open_pull_requests,
    list_recently_closed_issues,
    list_recently_merged_prs,
)

# Un PR se considera "estancado" si no tuvo actividad en este tiempo.
STALE_AFTER = timedelta(days=3)
# Ventana del resumen semanal.
WEEKLY_WINDOW = timedelta(days=7)


async def build_stale_pr_report(repos: list[str], now: datetime | None = None) -> str | None:
    """PRs abiertos sin actividad por más de STALE_AFTER. Devuelve None si no hay ninguno.

    Devolver None permite que el worker NO postee cuando no hay estancados (evita ruido
    diario de "no hay PRs estancados").
    """
    now = now or datetime.now(UTC)
    limite = now - STALE_AFTER

    secciones: list[str] = []
    for repo in repos:
        prs = await list_open_pull_requests(repo)
        estancados = [
            pr
            for pr in prs
            if datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00")) < limite
        ]
        if not estancados:
            continue
        lineas = [f"**{repo}** — {len(estancados)} PR(s) estancados (>3 días sin actividad):"]
        for pr in estancados:
            actualizado = pr["updated_at"][:10]  # solo la fecha
            lineas.append(
                f"• #{pr['number']} {pr['title']} — @{pr['author']} "
                f"— sin actividad desde {actualizado} — {pr['html_url']}"
            )
        secciones.append("\n".join(lineas))

    if not secciones:
        return None
    return "⚠️ **Stale PR Alert** · " + f"{now:%Y-%m-%d}\n\n" + "\n\n".join(secciones)


async def build_weekly_summary(repos: list[str], now: datetime | None = None) -> str:
    """Resumen semanal: PRs mergeados + issues cerrados en los últimos 7 días.

    Siempre devuelve texto (un resumen con 0/0 también es informativo).
    """
    now = now or datetime.now(UTC)
    desde = now - WEEKLY_WINDOW

    secciones: list[str] = []
    for repo in repos:
        merged = await list_recently_merged_prs(repo, desde)
        closed = await list_recently_closed_issues(repo, desde)
        lineas = [f"**{repo}** — {len(merged)} PR(s) mergeados · {len(closed)} issue(s) cerrados:"]
        for pr in merged:
            lineas.append(
                f"• ✅ PR #{pr['number']} {pr['title']} — @{pr['author']} — {pr['html_url']}"
            )
        for it in closed:
            lineas.append(f"• 🔒 issue #{it['number']} {it['title']} — {it['html_url']}")
        secciones.append("\n".join(lineas))

    encabezado = f"📊 **Weekly Summary** · {desde:%Y-%m-%d} → {now:%Y-%m-%d}"
    return encabezado + "\n\n" + "\n\n".join(secciones)
