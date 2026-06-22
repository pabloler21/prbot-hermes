"""Guardrail determinístico: allowlist de repos.

Lee config/guardrails/repo-allowlist.yaml y decide si se puede ACTUAR sobre un
repo. Se aplica en el WORKER (capa de código), nunca se confía en el LLM: a qué
repo se puede escribir es una decisión de código.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# Ruta al archivo de allowlist, calculada relativa a este módulo.
# __file__ = hermes_queue/guardrails.py  ->  parents[1] = raíz del repo.
ALLOWLIST_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "guardrails" / "repo-allowlist.yaml"
)


@lru_cache(maxsize=1)
def _load_allowed_repos() -> frozenset[str]:
    """Carga la lista de repos permitidos del YAML (cacheada: se lee una vez)."""
    data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    repos = data.get("allowed_repos") or []
    return frozenset(repos)


def is_repo_allowed(repo: str) -> bool:
    """True si 'owner/repo' está en la allowlist."""
    return repo in _load_allowed_repos()
