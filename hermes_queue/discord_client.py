"""Cliente para PUBLICAR mensajes en Discord vía un webhook entrante.

Un webhook entrante de Discord es una URL secreta asociada a un canal: un POST con
`{"content": ...}` publica el mensaje, sin bot ni conexión al gateway. Lo usamos para
trabajo recurrente que solo publica (el digest), donde un bot con gateway sería
sobredimensionado. La URL vive en DISCORD_DIGEST_WEBHOOK_URL (~/.hermes/.env), nunca
hardcodeada (quien tiene la URL puede postear en el canal: es una credencial).
"""

from __future__ import annotations

import os

import httpx

# Discord rechaza mensajes de más de 2000 caracteres; partimos el texto si hace falta.
DISCORD_MAX_CHARS = 2000


def _split_content(content: str, limit: int = DISCORD_MAX_CHARS) -> list[str]:
    """Parte el texto en trozos de <= limit caracteres, cortando por líneas.

    Si una sola línea supera el límite, la corta a la fuerza. Mantiene el orden.
    """
    if len(content) <= limit:
        return [content]

    chunks: list[str] = []
    current = ""
    for line in content.split("\n"):
        # +1 por el "\n" que reañadimos al unir.
        if current and len(current) + 1 + len(line) > limit:
            chunks.append(current)
            current = ""
        # Una línea más larga que el límite entero: la cortamos en pedazos duros.
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


async def post_to_discord(content: str) -> None:
    """Publica un mensaje en el canal del webhook (lo parte en varios si excede 2000).

    Lanza RuntimeError si falta la URL, y httpx errors ante fallos de red/HTTP.
    """
    url = os.environ.get("DISCORD_DIGEST_WEBHOOK_URL")
    if not url:
        raise RuntimeError("Falta DISCORD_DIGEST_WEBHOOK_URL en el entorno (~/.hermes/.env).")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for chunk in _split_content(content):
            response = await client.post(url, json={"content": chunk})
            response.raise_for_status()
