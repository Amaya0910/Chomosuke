"""cogs/meme.py"""

import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.meme_fetcher import MemeFetcher

logger = logging.getLogger("bump-bot")


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


class MemeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, meme_repo, meme_fetcher: MemeFetcher):
        self.bot = bot
        self.repo = meme_repo
        self.fetcher = meme_fetcher
        self.daily_meme.start()

    def cog_unload(self):
        self.daily_meme.cancel()

    @app_commands.command(name="setmemechannel", description="Configura el canal y la cantidad de memes diarios")
    @app_commands.describe(
        canal="Canal donde se publicarán los memes",
        hora="Hora del primer meme del día (0-23, UTC)",
        cantidad="Cuántos memes al día, distribuidos a lo largo del día (1-100)",
        subreddit="Subreddit opcional (si no lo pones, se eligen memes en español al azar)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_meme_channel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        hora: int = 12,
        cantidad: int = 1,
        subreddit: str = None,
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
        )

        horarios_legibles = times.replace(",", ", ")
        await interaction.followup.send(
            f"Listo, mandaré {cantidad} meme(s) al día en {canal.mention}, a las: {horarios_legibles} UTC.",
            ephemeral=True,
        )

    @app_commands.command(name="memenow", description="Manda un meme ahora mismo, sin esperar a la hora configurada (para probar)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def meme_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        cfg = self.repo.get_config(interaction.guild_id)
        if cfg is None:
            await interaction.followup.send(
                "Todavía no has configurado un canal de memes. Usa `/setmemechannel` primero.",
                ephemeral=True,
            )
            return

        meme = await self.fetcher.get_meme(cfg["subreddit"])
        if meme is None:
            await interaction.followup.send(
                "No pude traer un meme ahora mismo (la fuente falló). Intenta de nuevo en un momento.",
                ephemeral=True,
            )
            return

        try:
            webhook = discord.Webhook.from_url(cfg["webhook_url"], client=self.bot)
            embed = discord.Embed(title=meme["title"], url=meme["post_link"])
            embed.set_image(url=meme["image_url"])
            embed.set_footer(text=f"r/{meme['subreddit']}")
            await webhook.send(embed=embed, username="Meme del día")
        except discord.NotFound:
            await interaction.followup.send(
                "El webhook configurado ya no existe (puede que lo hayan borrado del canal). "
                "Vuelve a correr `/setmemechannel` para crear uno nuevo.",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.error(f"Error en /memenow para guild {interaction.guild_id}: {e}")
            await interaction.followup.send("Ocurrió un error al enviar el meme.", ephemeral=True)
            return

        await interaction.followup.send("Meme enviado.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def daily_meme(self):
        ahora = datetime.datetime.utcnow().strftime("%H:%M")
        configs = self.repo.get_all_configs()
        for cfg in configs:
            horarios = (cfg["times"] or "").split(",")
            if ahora in horarios:
                meme = await self.fetcher.get_meme(cfg["subreddit"])
                if meme is None:
                    continue
                try:
                    webhook = discord.Webhook.from_url(cfg["webhook_url"], client=self.bot)
                    embed = discord.Embed(title=meme["title"], url=meme["post_link"])
                    embed.set_image(url=meme["image_url"])
                    embed.set_footer(text=f"r/{meme['subreddit']}")
                    await webhook.send(embed=embed, username="Meme del día")
                except discord.NotFound:
                    logger.warning(f"Webhook inválido para guild {cfg['guild_id']}, fue borrado del canal.")
                except Exception as e:
                    logger.error(f"Error enviando meme a guild {cfg['guild_id']}: {e}")

    @daily_meme.before_loop
    async def before_daily_meme(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    pass  # se agrega manualmente en bot.py, no vía extension loader