import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from db.repositories import GuildConfigRepository

logger = logging.getLogger("bump-bot")


class BumpConfigCog(commands.GroupCog, name="bump-config", description="Configura el bot de bumps para este servidor"):
    """Comandos de administración. Solo depende de GuildConfigRepository (DIP)."""

    def __init__(self, bot: commands.Bot, repo: GuildConfigRepository):
        self.bot = bot
        self.repo = repo
        super().__init__()

    @app_commands.command(name="canal", description="Define el canal donde se avisa que ya se puede bumpear")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        self.repo.set_canal_aviso(interaction.guild_id, canal.id)
        await interaction.response.send_message(
            f"Listo. Los avisos de enfriamiento terminado se enviarán a {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="rol", description="Define el rol a mencionar cuando termina el enfriamiento (opcional)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rol(self, interaction: discord.Interaction, rol: discord.Role | None = None):
        self.repo.set_rol_aviso(interaction.guild_id, rol.id if rol else None)
        if rol:
            await interaction.response.send_message(f"Se mencionará a {rol.mention} en cada aviso.", ephemeral=True)
        else:
            await interaction.response.send_message("Se quitó la mención de rol en los avisos.", ephemeral=True)

    @app_commands.command(name="ver", description="Muestra la configuración actual del bot en este servidor")
    async def ver(self, interaction: discord.Interaction):
        config = self.repo.get(interaction.guild_id)
        if not config or not config["canal_aviso_id"]:
            await interaction.response.send_message(
                "Este servidor todavía no tiene canal de aviso configurado. Usa `/bump-config canal`.",
                ephemeral=True,
            )
            return

        canal_txt = f"<#{config['canal_aviso_id']}>"
        rol_txt = f"<@&{config['rol_aviso_id']}>" if config["rol_aviso_id"] else "Ninguno"
        estado = "Sin bump registrado todavía"
        if config["proximo_bump"]:
            proximo = datetime.fromisoformat(config["proximo_bump"])
            estado = f"Próximo aviso: <t:{int(proximo.timestamp())}:R>"

        await interaction.response.send_message(
            f"**Canal de aviso:** {canal_txt}\n**Rol mencionado:** {rol_txt}\n**Estado:** {estado}",
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Necesitas el permiso de 'Administrar servidor' para usar este comando.", ephemeral=True
            )
        else:
            logger.exception("Error en comando de configuración", exc_info=error)
            mensaje = "Ocurrió un error al ejecutar el comando."
            if interaction.response.is_done():
                await interaction.followup.send(mensaje, ephemeral=True)
            else:
                await interaction.response.send_message(mensaje, ephemeral=True)