"""cogs/meme.py"""

import datetime
import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.meme_service import MemeService
from services.meme_source import TIPO_VIDEO

logger = logging.getLogger("bump-bot")

LIMITE_TITULO = 200


def _calcular_horarios(hora_inicio: int, cantidad: int) -> str:
    """Distribuye 'cantidad' horarios a lo largo de 24 horas, empezando
    en 'hora_inicio'. Devuelve un string "HH:MM,HH:MM,..." listo para guardar."""
    total_minutos_dia = 24 * 60
    paso = total_minutos_dia // cantidad
    inicio_minutos = hora_inicio * 60
    horarios = []
    for i in range(cantidad):
        minutos = (inicio_minutos + i * paso) % total_minutos_dia
        h, m = divmod(minutos, 60)
        horarios.append(f"{h:02d}:{m:02d}")
    return ",".join(horarios)


def _origen(meme: dict) -> str:
    """Texto que indica de dónde viene el meme: lo define la propia fuente
    ('origen') y, si no lo trae, se asume un subreddit."""
    return meme.get("origen") or f"r/{meme['subreddit']}"


class MemeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, meme_repo, meme_service: MemeService):
        self.bot = bot
        self.repo = meme_repo
        self.service = meme_service
        self.daily_meme.start()

    def cog_unload(self):
        self.daily_meme.cancel()

    async def _publicar(self, cfg, meme: dict) -> None:
        """Envía el meme por webhook y lo registra en el historial solo si
        el envío salió bien. Las excepciones las maneja quien llama."""
        webhook = discord.Webhook.from_url(cfg["webhook_url"], client=self.bot)

        if meme["media_type"] == TIPO_VIDEO:
            await self._enviar_video(webhook, meme)
        else:
            await self._enviar_imagen(webhook, meme)

        self.service.marcar_enviado(cfg["guild_id"], meme)

    @staticmethod
    async def _enviar_imagen(webhook: discord.Webhook, meme: dict) -> None:
        embed = discord.Embed(title=meme["title"], url=meme["post_link"])
        embed.set_image(url=meme["media_url"])
        embed.set_footer(text=_origen(meme))
        await webhook.send(embed=embed, username="Michi momazos")

    @staticmethod
    async def _enviar_video(webhook: discord.Webhook, meme: dict) -> None:
        """Los embeds no reproducen video: se manda la URL del archivo como
        texto para que Discord muestre su reproductor. El enlace al post va
        entre <> para que no genere una segunda vista previa."""
        titulo = discord.utils.escape_markdown(meme["title"])[:LIMITE_TITULO]
        contenido = (
            f"**{titulo}**\n"
            f"{meme['media_url']}\n"
            f"-# {_origen(meme)} • <{meme['post_link']}>"
        )
        await webhook.send(
            content=contenido,
            username="Michi momazos",
            allowed_mentions=discord.AllowedMentions.none(),  # un título con @everyone no debe hacer ping
        )

    async def _enviar_ahora(
        self,
        interaction: discord.Interaction,
        tipo: str,
        subreddit: str | None,
    ) -> None:
        """Lógica común de /memenow y /memevideo: busca un meme nuevo del
        `tipo` pedido y lo publica en el canal configurado del servidor.
        Si `subreddit` es None se usa el que tenga configurado el servidor."""
        await interaction.response.defer(ephemeral=True)

        cfg = self.repo.get_config(interaction.guild_id)
        if cfg is None:
            await interaction.followup.send(
                "Todavía no has configurado un canal de memes. Usa `/setmemechannel` primero.",
                ephemeral=True,
            )
            return

        meme = await self.service.siguiente(interaction.guild_id, subreddit or cfg["subreddit"], tipo)
        if meme is None:
            await interaction.followup.send(
                "No encontré un meme nuevo ahora mismo (la fuente falló o ya se enviaron todos los disponibles). "
                "Intenta de nuevo en un momento.",
                ephemeral=True,
            )
            return

        try:
            await self._publicar(cfg, meme)
        except discord.NotFound:
            await interaction.followup.send(
                "El webhook configurado ya no existe (puede que lo hayan borrado del canal). "
                "Vuelve a correr `/setmemechannel` para crear uno nuevo.",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.error(f"Error enviando meme manual en guild {interaction.guild_id}: {e}")
            await interaction.followup.send("Ocurrió un error al enviar el meme.", ephemeral=True)
            return

        await interaction.followup.send("Meme enviado.", ephemeral=True)

    @app_commands.command(name="setmemechannel", description="Configura el canal y la cantidad de memes diarios")
    @app_commands.describe(
        canal="Canal donde se publicarán los memes",
        hora="Hora del primer Michi momazos (0-23, UTC)",
        cantidad="Cuántos memes al día, distribuidos a lo largo del día (1-100)",
        subreddit="Subreddit (imágenes) o comunidad de Lemmy nombre@instancia (videos). Opcional",
        tipo="Qué enviar: imagen, video o mixto (por defecto imagen)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_meme_channel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        hora: int = 12,
        cantidad: int = 1,
        subreddit: str = None,
        tipo: Literal["imagen", "video", "mixto"] = "imagen",
    ):
        await interaction.response.defer(ephemeral=True)

        cantidad = max(1, min(cantidad, 100))  # protege contra spam accidental

        webhooks = await canal.webhooks()
        webhook = discord.utils.get(webhooks, name="Meme Bot")
        if webhook is None:
            webhook = await canal.create_webhook(name="Meme Bot")

        times = _calcular_horarios(hora, cantidad)

        self.repo.set_config(
            guild_id=interaction.guild_id,
            channel_id=canal.id,
            webhook_url=webhook.url,
            times=times,
            subreddit=subreddit,
            media_mode=tipo,
        )

        horarios_legibles = times.replace(",", ", ")
        await interaction.followup.send(
            f"Listo, mandaré {cantidad} meme(s) de tipo **{tipo}** al día en {canal.mention}, "
            f"a las: {horarios_legibles} UTC.",
            ephemeral=True,
        )

    @app_commands.command(name="memenow", description="Manda un meme ahora mismo, sin esperar a la hora configurada (para probar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def meme_now(self, interaction: discord.Interaction):
        cfg = self.repo.get_config(interaction.guild_id)
        tipo = cfg["media_mode"] if cfg else "imagen"
        await self._enviar_ahora(interaction, tipo, subreddit=None)

    @app_commands.command(name="memevideo", description="Manda un meme en video ahora mismo, sin esperar a la hora configurada")
    @app_commands.describe(comunidad="Comunidad de Lemmy opcional, ej. memes@lemmy.world (si no, usa la lista por defecto)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def meme_video(self, interaction: discord.Interaction, comunidad: str | None = None):
        await self._enviar_ahora(interaction, TIPO_VIDEO, comunidad)

    @tasks.loop(minutes=1)
    async def daily_meme(self):
        ahora = datetime.datetime.utcnow().strftime("%H:%M")
        for cfg in self.repo.get_all_configs():
            horarios = (cfg["times"] or "").split(",")
            if ahora not in horarios:
                continue

            meme = await self.service.siguiente(cfg["guild_id"], cfg["subreddit"], cfg["media_mode"])
            if meme is None:
                logger.warning(f"[{cfg['guild_id']}] No se encontró un meme nuevo para las {ahora} UTC.")
                continue

            try:
                await self._publicar(cfg, meme)
            except discord.NotFound:
                logger.warning(f"Webhook inválido para guild {cfg['guild_id']}, fue borrado del canal.")
            except Exception as e:
                logger.error(f"Error enviando meme a guild {cfg['guild_id']}: {e}")

    @daily_meme.before_loop
    async def before_daily_meme(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    pass  # se agrega manualmente en bot.py, no vía extension loader