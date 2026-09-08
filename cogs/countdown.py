import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db.countdown_repository import CountdownConfigRepository
from services.countdown_calculator import CountdownCalculator

logger = logging.getLogger("bump-bot")

ZONA_COLOMBIA = ZoneInfo("America/Bogota")
HORA_ENVIO = time(hour=14, minute=0, tzinfo=ZONA_COLOMBIA)  # 2:00 p.m. Colombia


class CountdownConfigCog(
    commands.GroupCog,
    name="countdown-config",
    description="Configura el canal del contador hacia el 1 de agosto de 2027",
):
    """Comandos de administración. Solo depende de CountdownConfigRepository (DIP)."""

    def __init__(self, bot: commands.Bot, repo: CountdownConfigRepository):
        self.bot = bot
        self.repo = repo
        super().__init__()

    @app_commands.command(name="canal", description="Define el canal donde se publica el contador diario")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        self.repo.set_canal(interaction.guild_id, canal.id)
        await interaction.response.send_message(
            f"Listo. El contador se publicará todos los días a las 2:00 p.m. (Colombia) en {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="ver", description="Muestra en qué canal está configurado el contador")
    async def ver(self, interaction: discord.Interaction):
        canal_id = self.repo.get_canal(interaction.guild_id)
        if not canal_id:
            await interaction.response.send_message(
                "Este servidor no tiene canal configurado. Usa `/countdown-config canal`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(f"El contador se publica en <#{canal_id}>.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Necesitas el permiso de 'Administrar servidor' para usar este comando.", ephemeral=True
            )
        else:
            logger.exception("Error en comando de countdown-config", exc_info=error)
            mensaje = "Ocurrió un error al ejecutar el comando."
            if interaction.response.is_done():
                await interaction.followup.send(mensaje, ephemeral=True)
            else:
                await interaction.response.send_message(mensaje, ephemeral=True)


class CountdownCog(commands.Cog):
    """Publica diariamente a las 2:00 p.m. (Colombia) los días restantes y el
    porcentaje de avance hacia la fecha objetivo, en el canal configurado de
    cada servidor. También expone /countdown para consultarlo en cualquier
    momento sin esperar al envío diario.
    """

    def __init__(self, bot: commands.Bot, repo: CountdownConfigRepository, calculator: CountdownCalculator):
        self.bot = bot
        self.repo = repo
        self.calculator = calculator
        self.publicar_diario.start()

    def cog_unload(self):
        self.publicar_diario.cancel()

    def _mensaje(self) -> str:
        estado = self.calculator.calcular(datetime.now(ZONA_COLOMBIA).date())
        if estado.finalizado:
            return f"🎉 ¡Hoy es el día! Se cumplió la meta del {self.calculator.fecha_fin.strftime('%d/%m/%Y')}."
        return (
            f"📅 Faltan **{estado.dias_restantes} días** para el {self.calculator.fecha_fin.strftime('%d/%m/%Y')}.\n"
            f"📊 Progreso: **{estado.porcentaje}%** (desde el {self.calculator.fecha_inicio.strftime('%d/%m/%Y')})."
        )

    @app_commands.command(name="countdown", description="Muestra el contador de días y el porcentaje de avance")
    async def countdown(self, interaction: discord.Interaction):
        await interaction.response.send_message(self._mensaje())

    @tasks.loop(time=HORA_ENVIO)
    async def publicar_diario(self):
        mensaje = self._mensaje()
        for fila in self.repo.all_configured():
            guild = self.bot.get_guild(fila["guild_id"])
            if guild is None:
                continue
            canal = guild.get_channel(fila["canal_id"])
            if canal is None:
                logger.error(f"[{fila['guild_id']}] El canal del countdown ya no existe.")
                continue
            try:
                await canal.send(mensaje)
            except discord.Forbidden:
                logger.error(f"[{fila['guild_id']}] Sin permisos para enviar el countdown.")
            except discord.HTTPException as e:
                logger.warning(f"[{fila['guild_id']}] No se pudo enviar el countdown: {e}")

    @publicar_diario.before_loop
    async def antes_de_publicar(self):
        await self.bot.wait_until_ready()