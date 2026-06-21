"""Configuración de conexión a Redis para arq (la usan workers y productores).

Construye un RedisSettings de arq a partir de REDIS_URL, que vive en
~/.hermes/.env (chmod 600) en el VPS. El secreto NO se hardcodea.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from arq.connections import RedisSettings


def redis_settings_from_env() -> RedisSettings:
    """Lee REDIS_URL del entorno y la traduce a un RedisSettings de arq."""
    url = os.environ.get("REDIS_URL")
    if not url:
        # Fail-closed: sin URL no arrancamos. Mejor un error claro acá que un
        # fallo raro de conexión más adelante.
        raise RuntimeError(
            "Falta REDIS_URL en el entorno. Cargala en ~/.hermes/.env "
            "(ver deploy/install-notes.md, sección 9)."
        )

    # urlparse separa la URL redis://:password@host:port en sus componentes.
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        # Con requirepass no hay usuario; redis usa solo la password.
        password=parsed.password or None,
        # rediss:// = TLS. Nuestro Redis local es redis:// (sin TLS).
        ssl=parsed.scheme == "rediss",
    )
