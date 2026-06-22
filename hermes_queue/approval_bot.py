"""Bot de Discord que opera el approval gate (el dueño determinístico de los botones).

Escucha por pub/sub los pedidos pendientes que publica el MCP, los muestra en el
canal de aprobaciones con botones ✅/❌, y SOLO un usuario de la allowlist puede
aprobar/rechazar. Al aprobar, mueve el pedido a la cola real y reporta el resultado.

Es un bot SEPARADO de Hermes (su propio token): no forkeamos Hermes, así que los
botones custom los maneja este proceso.

Correr (en el VPS):  uv run python -m hermes_queue.approval_bot
"""

from __future__ import annotations

import asyncio
import json
import os

import discord
from arq import create_pool
from arq.connections import ArqRedis
from arq.jobs import Job

from hermes_queue.events import PENDING_CHANNEL
from hermes_queue.jobs.post_comment import approve, reject
from hermes_queue.settings import redis_settings_from_env


def _allowed_user_ids() -> set[int]:
    """IDs de Discord autorizados a aprobar (de DISCORD_ALLOWED_USERS)."""
    raw = os.environ.get("DISCORD_ALLOWED_USERS", "")
    return {int(x) for x in raw.split(",") if x.strip()}


def _format_request(data: dict) -> str:
    """Texto del pedido pendiente para mostrar en Discord."""
    return (
        f"**Pedido de comentario** en `{data['repo']}` · PR #{data['pr_number']}\n"
        f"> {data['body']}\n\n"
        f"¿Aprobar?"
    )


class ApprovalView(discord.ui.View):
    """Botones ✅/❌ para un pedido pendiente concreto."""

    def __init__(self, pool: ArqRedis, approval_id: str) -> None:
        # timeout=None: los botones no expiran mientras el bot esté vivo.
        super().__init__(timeout=None)
        self.pool = pool
        self.approval_id = approval_id

    async def _is_authorized(self, interaction: discord.Interaction) -> bool:
        """Gate determinístico: solo usuarios de la allowlist aprueban/rechazan."""
        if interaction.user.id in _allowed_user_ids():
            return True
        await interaction.response.send_message(
            "No estás autorizado a aprobar o rechazar.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Aprobar", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._is_authorized(interaction):
            return
        # Sacamos los botones y avisamos dentro del límite de 3s de Discord.
        await interaction.response.edit_message(
            content=f"⏳ Aprobado por {interaction.user.mention}. Encolando…", view=None
        )
        moved = await approve(self.pool, self.approval_id)
        if not moved:
            await interaction.edit_original_response(
                content="⚠️ El pedido ya no existe (expiró o ya se resolvió)."
            )
            return
        # El resultado del worker puede tardar (reintentos): lo esperamos aparte.
        asyncio.create_task(self._report_result(interaction))

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._is_authorized(interaction):
            return
        await reject(self.pool, self.approval_id)
        await interaction.response.edit_message(
            content=f"❌ Rechazado por {interaction.user.mention}. No se posteó nada.",
            view=None,
        )

    async def _report_result(self, interaction: discord.Interaction) -> None:
        """Espera el resultado del worker y edita el mensaje con el desenlace."""
        job = Job(self.approval_id, self.pool)
        try:
            result = await job.result(timeout=120)
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"⚠️ No pude confirmar el resultado en 120s: {exc}"
            )
            return
        if result:
            await interaction.edit_original_response(content=f"✅ Comentario posteado: {result}")
        else:
            await interaction.edit_original_response(
                content="⚠️ El worker rechazó el pedido (allowlist o error). Ver logs."
            )


class ApprovalBot(discord.Client):
    """Cliente que escucha pendientes por pub/sub y muestra los botones."""

    def __init__(self) -> None:
        # Intents por defecto: alcanzan para enviar mensajes y recibir clicks de
        # botones (las interacciones llegan sin intents privilegiados).
        super().__init__(intents=discord.Intents.default())
        self.pool: ArqRedis | None = None

    async def setup_hook(self) -> None:
        # Se ejecuta una vez, al iniciar: abrimos la conexión y arrancamos el listener.
        self.pool = await create_pool(redis_settings_from_env())
        asyncio.create_task(self._listen_pending())

    async def _listen_pending(self) -> None:
        await self.wait_until_ready()
        assert self.pool is not None

        channel_id = int(os.environ["DISCORD_APPROVAL_CHANNEL_ID"])
        channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)

        # Nos suscribimos al canal pub/sub y reaccionamos a cada pedido pendiente.
        pubsub = self.pool.pubsub()
        await pubsub.subscribe(PENDING_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            view = ApprovalView(self.pool, data["approval_id"])
            await channel.send(_format_request(data), view=view)


def main() -> None:
    token = os.environ["DISCORD_APPROVAL_BOT_TOKEN"]
    ApprovalBot().run(token)


if __name__ == "__main__":
    main()
