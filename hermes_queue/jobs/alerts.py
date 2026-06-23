"""Formateadores de los alerts de POLL: New Issue Alert y Deploy Notification (Fase 6b).

A diferencia de los reportes, los alerts son CON ESTADO (cursor + dedup), así que la
orquestación (leer cursor, traer lo nuevo, marcar visto, postear) vive en el worker. Acá
solo formateamos los items ya filtrados en Markdown — lógica pura, fácil de testear.
"""

from __future__ import annotations


def format_new_issues(repo: str, issues: list[dict]) -> str:
    """Mensaje de issues nuevos detectados en un repo."""
    lineas = [f"🆕 **New Issue Alert** · `{repo}` — {len(issues)} issue(s) nuevo(s):"]
    for it in issues:
        labels = f" [{', '.join(it['labels'])}]" if it.get("labels") else ""
        lineas.append(
            f"• #{it['number']} {it['title']} — @{it['author']}{labels} — {it['html_url']}"
        )
    return "\n".join(lineas)


def format_deploys(repo: str, prs: list[dict]) -> str:
    """Mensaje de PRs mergeados a la rama de deploy (p. ej. main)."""
    lineas = [f"🚀 **Deploy Notification** · `{repo}` — {len(prs)} merge(s) a la rama de deploy:"]
    for pr in prs:
        fecha = pr["merged_at"][:10]
        lineas.append(
            f"• PR #{pr['number']} {pr['title']} — @{pr['author']} "
            f"— mergeado {fecha} — {pr['html_url']}"
        )
    return "\n".join(lineas)
