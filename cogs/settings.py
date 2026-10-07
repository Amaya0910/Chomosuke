import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.countdown import HORA_ENVIO
from config import Config
from db.countdown_repository import CountdownConfigRepository
from db.repositories import GuildConfigRepository, MemeConfigRepository
from services.countdown_calculator import CountdownCalculator

logger = logging.getLogger("bump-bot")

NO_CONFIGURADO = "No configurado"


def _formatear_segundos(total: int) -> str:
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    partes = []
    if horas:
        partes.append(f"{horas}h")
    if minutos:
        partes.append(f"{minutos}m")
    if segundos or not partes:
        partes.append(f"{segundos}s")
    return " ".join(partes)


def _formatear_fuente(valor: str | None) -> str:
    """Una comunidad de Lemmy lleva '@' y se muestra como !nombre@instancia;
    cualquier otro valor es un subreddit y se muestra como r/nombre."""
    if not valor:
        return "Aleatoria"
    return f"!{valor}" if "@" in valor else f"r/{valor}"


class SettingsCog(commands.Cog):
    """Comando /configuracion: muestra en un mensaje público toda la
    configuración actual del bot en el servidor. Solo lee; no modifica nada.

    Nunca expone secretos (token, URL del webhook, ruta de la base de datos).
    """

    def __init__(
        self,
        bot: commands.Bot,
        config: Config,
        bump_repo: GuildConfigRepository,
        countdown_repo: CountdownConfigRepository,
        meme_repo: MemeConfigRepository,
        calculator: CountdownCalculator,
    ):
        self.bot = bot
        self.config = config
        self.bump_repo = bump_repo
        self.countdown_repo = countdown_repo
        self.meme_repo = meme_repo
        self.calculator = calculator

    def _campo_bump(self, guild_id: int) -> str:
        cfg = self.bump_repo.get(guild_id)
        canal = f"<#{cfg['canal_aviso_id']}>" if cfg and cfg["canal_aviso_id"] else NO_CONFIGURADO
        rol = f"<@&{cfg['rol_aviso_id']}>" if cfg and cfg["rol_aviso_id"] else "Ninguno"

        if cfg and cfg["proximo_bump"]:
            proximo = datetime.fromisoformat(cfg["proximo_bump"])
            if proximo > datetime.now(timezone.utc):
                estado = f"Próximo aviso <t:{int(proximo.timestamp())}:R>"
            else:
                estado = "Ya se puede bumpear"
        else:
            estado = "Sin bump registrado todavía"

        return (
            f"**Canal de aviso:** {canal}\n"
            f"**Rol mencionado:** {rol}\n"
            f"**Enfriamiento:** {_formatear_segundos(self.config.cooldown_seconds)}\n"
            f"**Emoji:** {self.config.bump_emoji}\n"
            f"**Estado:** {estado}"
        )

    def _campo_countdown(self, guild_id: int) -> str:
        canal_id = self.countdown_repo.get_canal(guild_id)
        canal = f"<#{canal_id}>" if canal_id else NO_CONFIGURADO
        hora = HORA_ENVIO.strftime("%I:%M %p").lstrip("0").lower().replace("am", "a.m.").replace("pm", "p.m.")
        inicio = self.calculator.fecha_inicio.strftime("%d/%m/%Y")
        fin = self.calculator.fecha_fin.strftime("%d/%m/%Y")

        return (
            f"**Canal:** {canal}\n"
            f"**Envío diario:** {hora} (Colombia)\n"
            f"**Rango:** {inicio} → {fin}"
        )

    def _campo_memes(self, guild_id: int) -> str:
        cfg = self.meme_repo.get_config(guild_id)
        if cfg is None:
            return NO_CONFIGURADO

        horarios = [h for h in (cfg["times"] or "").split(",") if h]
        horarios_txt = ", ".join(horarios) or "Ninguno"
        if len(horarios_txt) > 600:  # evita pasar el límite de 1024 chars por campo
            horarios_txt = horarios_txt[:600] + "…"

        return (
            f"**Canal:** <#{cfg['channel_id']}>\n"
            f"**Tipo:** {cfg['media_mode']}\n"
            f"**Memes al día:** {len(horarios)}\n"
            f"**Horarios (UTC):** {horarios_txt}\n"
            f"**Fuente fija:** {_formatear_fuente(cfg['subreddit'])}"
        )

    @app_commands.command(name="configuracion", description="Muestra la configuración actual del bot en este servidor")
    @app_commands.guild_only()
    async def configuracion(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id

        embed = discord.Embed(title="⚙️ Configuración del bot", color=discord.Color.blurple())
        embed.add_field(name="🔔 Bump", value=self._campo_bump(guild_id), inline=False)
        embed.add_field(name="📅 Countdown", value=self._campo_countdown(guild_id), inline=False)
        embed.add_field(name="😹 Memes", value=self._campo_memes(guild_id), inline=False)
        embed.set_footer(text=f"Servidor: {interaction.guild.name}")

        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.exception("Error en /configuracion", exc_info=error)
        mensaje = "Ocurrió un error al ejecutar el comando."
        if interaction.response.is_done():
            await interaction.followup.send(mensaje, ephemeral=True)
        else:
            await interaction.response.send_message(mensaje, ephemeral=True)