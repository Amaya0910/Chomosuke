"""bot.py"""

import logging

import discord
from discord.ext import commands

from config import Config
from db.database import Database
from db.repositories import SQLiteGuildConfigRepository, SQLiteMemeConfigRepository
from db.countdown_repository import SQLiteCountdownConfigRepository
from db.meme_history_repository import SQLiteMemeHistoryRepository
from services.disboard_classifier import DisboardMessageClassifier
from services.scheduler import TimerScheduler
from services.countdown_calculator import CountdownCalculator
from services.lemmy_video_fetcher import LemmyVideoFetcher
from services.meme_fetcher import MemeFetcher
from services.meme_service import MemeService
from services.meme_source import TIPO_IMAGEN, TIPO_VIDEO
from cogs.bump import BumpCog
from cogs.bump_config_commands import BumpConfigCog
from cogs.alarm import AlarmCog
from cogs.countdown import CountdownCog, CountdownConfigCog
from cogs.meme import MemeCog
from cogs.settings import SettingsCog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bump-bot")


class BumpBot(commands.Bot):
    """Composition root: arma las implementaciones concretas y las inyecta
    en los cogs a través de sus constructores. Si mañana cambias SQLite por
    otra base de datos, solo tocas esta clase."""

    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.database = Database(config.db_path)
        self.repo = SQLiteGuildConfigRepository(self.database)
        self.countdown_repo = SQLiteCountdownConfigRepository(self.database)
        self.meme_repo = SQLiteMemeConfigRepository(self.database)
        self.meme_history_repo = SQLiteMemeHistoryRepository(self.database)
        self.scheduler = TimerScheduler()
        self.classifier = DisboardMessageClassifier()
        self.countdown_calculator = CountdownCalculator(config.countdown_start, config.countdown_end)
        self.meme_service = MemeService(
            sources={
                TIPO_IMAGEN: MemeFetcher(),
                TIPO_VIDEO: LemmyVideoFetcher(),
            },
            history=self.meme_history_repo,
        )

    async def setup_hook(self):
        await self.add_cog(BumpCog(self, self.config, self.repo, self.scheduler, self.classifier))
        await self.add_cog(BumpConfigCog(self, self.repo))
        await self.add_cog(AlarmCog(self, self.scheduler))
        await self.add_cog(CountdownConfigCog(self, self.countdown_repo))
        await self.add_cog(CountdownCog(self, self.countdown_repo, self.countdown_calculator))
        await self.add_cog(MemeCog(self, self.meme_repo, self.meme_service))
        await self.add_cog(
            SettingsCog(
                self,
                self.config,
                self.repo,
                self.countdown_repo,
                self.meme_repo,
                self.countdown_calculator,
            )
        )
        synced = await self.tree.sync()
        logger.info(f"Comandos sincronizados: {[c.name for c in synced]}")

    async def on_ready(self):
        logger.info(f"Bot encendido y conectado como {self.user}")


def main():
    config = Config.from_env()
    bot = BumpBot(config)
    bot.run(config.token)


if __name__ == "__main__":
    main()