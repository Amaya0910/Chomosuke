import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from services.duration_parser import DurationParseError, parse_duration
from services.scheduler import TimerScheduler

logger = logging.getLogger("bump-bot")


class AlarmCog(commands.Cog):
    """Comando /alarm: avisa en el canal cuando pasa el tiempo indicado.

    Reutiliza el mismo TimerScheduler que usa el recordatorio de bump, sin
    conocer nada de Disboard ni de guild_config (SRP + reutilización sin
    duplicar lógica de temporizadores).
    """

    def __init__(self, bot: commands.Bot, scheduler: TimerScheduler):
        self.bot = bot
        self.scheduler = scheduler
        self._contador = 0

    @app_commands.command(name="alarm", description="Te avisa en este canal cuando pase el tiempo indicado")
    @app_commands.describe(
        duracion="Ej: 30s, 5m, 1h20m (máximo 24h)",
        motivo="Texto opcional para recordarte de qué se trata",
    )
    async def alarm(self, interaction: discord.Interaction, duracion: str, motivo: str | None = None):
        try:
            segundos = parse_duration(duracion)
        except DurationParseError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        self._contador += 1
        clave = f"alarm:{interaction.channel_id}:{interaction.user.id}:{self._contador}"

        objetivo = datetime.now(timezone.utc) + timedelta(seconds=segundos)
        aviso = f"⏰ Listo {interaction.user.mention}, te aviso <t:{int(objetivo.timestamp())}:R>"
        if motivo:
            aviso += f" — *{motivo}*"
        await interaction.response.send_message(aviso)

        canal = interaction.channel
        usuario = interaction.user

        async def avisar():
            try:
                texto = f"⏰ {usuario.mention} ¡tu alarma de `{duracion}` terminó!"
                if motivo:
                    texto += f" — *{motivo}*"
                await canal.send(texto)
            except discord.Forbidden:
                logger.error(f"Sin permisos para enviar la alarma en el canal {canal.id}")
            except discord.HTTPException as e:
                logger.warning(f"No se pudo enviar la alarma: {e}")

        self.scheduler.programar(clave, segundos, avisar, reemplazar=False)