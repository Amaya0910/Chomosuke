"""cogs/meme.py"""

import datetime
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.meme_fetcher import MemeFetcher

logger = logging.getLogger("bump-bot")


class MemeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, meme_repo, meme_fetcher: MemeFetcher):
        self.bot = bot
        self.repo = meme_repo
        self.fetcher = meme_fetcher
        self.daily_meme.start()

    def cog_unload(self):
        self.daily_meme.cancel()

    @app_commands.command(name="setmemechannel", description="Configura el canal donde se enviarán memes diarios")
    @app_commands.describe(canal="Canal donde se publicarán los memes", hora="Hora del día (0-23, UTC)", subreddit="Subreddit opcional")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_meme_channel(self, interaction: discord.Interaction, canal: discord.TextChannel, hora: int = 12, subreddit: str = None):
        await interaction.response.defer(ephemeral=True)

        webhooks = await canal.webhooks()
        webhook = discord.utils.get(webhooks, name="Meme Bot")
        if webhook is None:
            webhook = await canal.create_webhook(name="Meme Bot")

        self.repo.set_config(
            guild_id=interaction.guild_id,
            channel_id=canal.id,
            webhook_url=webhook.url,
            hour=hora,
            minute=0,
            subreddit=subreddit,
        )

        await interaction.followup.send(
            f"Listo, mandaré memes en {canal.mention} todos los días a las {hora}:00 UTC.",
            ephemeral=True,
        )

    @tasks.loop(minutes=1)
    async def daily_meme(self):
        now = datetime.datetime.utcnow()
        configs = self.repo.get_all_configs()
        for cfg in configs:
            if cfg["hour"] == now.hour and cfg["minute"] == now.minute:
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