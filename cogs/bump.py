import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from config import Config
from db.repositories import GuildConfigRepository
from services.disboard_classifier import DisboardMessageClassifier
from services.scheduler import TimerScheduler

logger = logging.getLogger("bump-bot")


class BumpCog(commands.Cog):
    """Escucha los mensajes de Disboard y gestiona el recordatorio de bump.

    Depende de abstracciones (GuildConfigRepository, TimerScheduler,
    DisboardMessageClassifier) inyectadas por el bot, no de implementaciones
    concretas: se pueden sustituir o testear de forma independiente (DIP).
    """

    def __init__(
        self,
        bot: commands.Bot,
        config: Config,
        repo: GuildConfigRepository,
        scheduler: TimerScheduler,
        classifier: DisboardMessageClassifier,
    ):
        self.bot = bot
        self.config = config
        self.repo = repo
        self.scheduler = scheduler
        self.classifier = classifier

    def _clave(self, guild_id: int) -> str:
        return f"bump:{guild_id}"

    @commands.Cog.listener()
    async def on_ready(self):
        for fila in self.repo.all_pending():
            proximo = datetime.fromisoformat(fila["proximo_bump"])
            restante = (proximo - datetime.now(timezone.utc)).total_seconds()
            logger.info(f"[{fila['guild_id']}] Retomando temporizador: {max(restante, 0):.0f}s restantes")
            self._programar(fila["guild_id"], max(restante, 0))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.id != self.config.disboard_id:
            return
        if not message.embeds:
            return

        clasificacion = self.classifier.clasificar(message.embeds[0])
        guild = message.guild

        if clasificacion == "enfriamiento":
            await self._borrar_tras(message, 3)
            return

        if clasificacion == "desconocido":
            logger.warning(f"[{guild.id}] Embed de Disboard no reconocido, se ignora.")
            return

        await self._manejar_exito(guild, message)

    async def _manejar_exito(self, guild: discord.Guild, message: discord.Message):
        config = self.repo.get(guild.id)
        if config:
            await self._borrar_mensaje_previo(guild, config["canal_aviso_id"], config["mensaje_id"])

        await self._borrar_tras(message, 3)

        proximo_bump = datetime.now(timezone.utc) + timedelta(seconds=self.config.cooldown_seconds)
        self.repo.set_estado(guild.id, proximo_bump, None)
        self._programar(guild.id, self.config.cooldown_seconds - 3)
        logger.info(f"[{guild.id}] Bump confirmado. Próximo aviso en {self.config.cooldown_seconds}s.")

    async def _borrar_tras(self, message: discord.Message, segundos: float):
        await asyncio.sleep(segundos)
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _borrar_mensaje_previo(self, guild: discord.Guild, canal_id, mensaje_id):
        if not mensaje_id or not canal_id:
            return
        canal = guild.get_channel(canal_id)
        if canal is None:
            return
        try:
            mensaje_previo = await canal.fetch_message(mensaje_id)
            await mensaje_previo.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            logger.error(f"[{guild.id}] Sin permisos para borrar el recordatorio anterior.")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.id}] No se pudo borrar el recordatorio anterior: {e}")

    def _programar(self, guild_id: int, segundos: float):
        self.scheduler.programar(self._clave(guild_id), segundos, lambda: self._avisar(guild_id))

    async def _avisar(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            logger.error(f"No se pudo encontrar el servidor {guild_id} al terminar el temporizador.")
            return

        config = self.repo.get(guild_id)
        if not config or not config["canal_aviso_id"]:
            logger.warning(f"[{guild_id}] No hay canal de aviso configurado. Usa /bump-config canal.")
            return

        canal = guild.get_channel(config["canal_aviso_id"])
        if canal is None:
            logger.error(f"[{guild_id}] El canal de aviso configurado ya no existe.")
            return

        mencion = f"<@&{config['rol_aviso_id']}> " if config["rol_aviso_id"] else ""
        try:
            mensaje_enviado = await canal.send(
                f"{mencion}**¡El enfriamiento ha terminado!** Ya pueden usar `/bump` nuevamente. {self.config.bump_emoji}"
            )
            self.repo.set_estado(guild_id, datetime.now(timezone.utc), mensaje_enviado.id)
        except discord.Forbidden:
            logger.error(f"[{guild_id}] Sin permisos para enviar mensajes en el canal de aviso.")