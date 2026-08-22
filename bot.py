"""bot.py"""

import logging

import discord
from discord.ext import commands

from config import Config
from db.database import Database
from db.repositories import SQLiteGuildConfigRepository, SQLiteMemeConfigRepository  # <-- agregado SQLiteMemeConfigRepository
from services.disboard_classifier import DisboardMessageClassifier
from services.scheduler import TimerScheduler
from services.meme_fetcher import MemeFetcher  # <-- nuevo import
from cogs.bump import BumpCog
from cogs.bump_config_commands import BumpConfigCog
from cogs.alarm import AlarmCog
from cogs.meme import MemeCog  # <-- nuevo import

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bump-bot")


class BumpBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.database = Database(config.db_path)
        self.repo = SQLiteGuildConfigRepository(self.database)
        self.scheduler = TimerScheduler()
        self.classifier = DisboardMessageClassifier()

        # --- agregado ---
        self.meme_repo = SQLiteMemeConfigRepository(self.database)
        self.meme_fetcher = MemeFetcher()
        # ----------------

    async def setup_hook(self):
        await self.add_cog(BumpCog(self, self.config, self.repo, self.scheduler, self.classifier))
        await self.add_cog(BumpConfigCog(self, self.repo))
        await self.add_cog(AlarmCog(self, self.scheduler))

        # --- agregado ---
        await self.add_cog(MemeCog(self, self.meme_repo, self.meme_fetcher))
        # ----------------

        await self.tree.sync()

    async def on_ready(self):
        logger.info(f"Bot encendido y conectado como {self.user}")


def main():
    config = Config.from_env()
    bot = BumpBot(config)
    bot.run(config.token)


if __name__ == "__main__":
    main()